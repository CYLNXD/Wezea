"""
Newsletter Router — Abonnement, confirmation double opt-in, désabonnement
=========================================================================
Endpoints :
  POST /newsletter/subscribe       Demande d'abonnement (envoie email de confirmation)
  GET  /newsletter/confirm/{token} Confirmation double opt-in (lien dans l'email)
  POST /newsletter/unsubscribe     Désabonnement par email
"""
import asyncio
import logging
import os
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.limiter import limiter
from app.models import NewsletterSubscription
from app.services import brevo_service

logger = logging.getLogger("cyberhealth.newsletter")

router = APIRouter(prefix="/newsletter", tags=["Newsletter"])

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://wezea.net")
TOKEN_EXPIRE_HOURS = 48


# ── Schémas ───────────────────────────────────────────────────────────────────

class SubscribeRequest(BaseModel):
    email: EmailStr

class UnsubscribeRequest(BaseModel):
    email: EmailStr


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_ip(request: Request) -> str:
    """Récupère l'IP du client (prend en compte les proxies)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── POST /newsletter/subscribe ────────────────────────────────────────────────

@router.post("/subscribe", status_code=202)
@limiter.limit("5/minute")
async def subscribe(
    request: Request,
    body: SubscribeRequest = Body(...),
    db: Session = Depends(get_db),
):
    """
    Enregistre une demande d'abonnement et envoie un email de confirmation
    (double opt-in RGPD).
    """
    email = body.email.lower().strip()

    # Vérifie si une souscription confirmée existe déjà
    existing = db.query(NewsletterSubscription).filter_by(email=email).first()

    if existing:
        if existing.confirmed and not existing.unsubscribed:
            # Déjà abonné — on ne révèle pas l'info mais on renvoie 202 silencieusement
            return JSONResponse({"status": "pending"})
        if existing.unsubscribed:
            # Ré-abonnement après désabonnement : on réactive
            existing.unsubscribed = False
            existing.confirmed    = False
            existing.confirmed_at = None
            existing.token        = secrets.token_urlsafe(32)
            existing.created_at   = datetime.now(timezone.utc)
            existing.ip_address   = _get_ip(request)
            db.commit()
            asyncio.create_task(
                brevo_service.send_newsletter_confirmation_email(email, existing.token)
            )
            return JSONResponse({"status": "pending"})
        # Déjà en attente de confirmation — renvoi du même token
        if existing.token:
            asyncio.create_task(
                brevo_service.send_newsletter_confirmation_email(email, existing.token)
            )
        return JSONResponse({"status": "pending"})

    # Nouveau contact
    token = secrets.token_urlsafe(32)
    sub = NewsletterSubscription(
        email      = email,
        token      = token,
        confirmed  = False,
        ip_address = _get_ip(request),
    )
    db.add(sub)
    db.commit()

    asyncio.create_task(
        brevo_service.send_newsletter_confirmation_email(email, token)
    )

    return JSONResponse({"status": "pending"})


# ── GET /newsletter/confirm/{token} ──────────────────────────────────────────

@router.get("/confirm/{token}")
async def confirm(
    token: str,
    db: Session = Depends(get_db),
):
    """
    Confirme l'abonnement via le lien reçu par email.
    Redirige vers le frontend avec un paramètre de succès.
    """
    sub = db.query(NewsletterSubscription).filter_by(token=token).first()

    if not sub:
        raise HTTPException(status_code=404, detail="Lien de confirmation invalide ou expiré.")

    # Vérifie l'expiration du token (48h)
    if sub.created_at:
        age = datetime.now(timezone.utc) - sub.created_at.replace(tzinfo=timezone.utc)
        if age > timedelta(hours=TOKEN_EXPIRE_HOURS):
            raise HTTPException(
                status_code=410,
                detail="Ce lien de confirmation a expiré. Veuillez vous réinscrire."
            )

    if not sub.confirmed:
        sub.confirmed    = True
        sub.confirmed_at = datetime.now(timezone.utc)
        sub.token        = None   # invalide le token après usage
        db.commit()

        # Ajout à Brevo + email de bienvenue en arrière-plan
        asyncio.create_task(brevo_service.add_newsletter_contact(sub.email))
        asyncio.create_task(brevo_service.send_newsletter_welcome_email(sub.email))

    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"{FRONTEND_URL}/?newsletter_confirmed=1", status_code=302)


# ── POST /newsletter/unsubscribe ──────────────────────────────────────────────

@router.post("/unsubscribe", status_code=200)
@limiter.limit("10/minute")
async def unsubscribe(
    body: UnsubscribeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Désabonnement immédiat."""
    email = body.email.lower().strip()
    sub = db.query(NewsletterSubscription).filter_by(email=email).first()

    if sub and not sub.unsubscribed:
        sub.unsubscribed = True
        db.commit()
        asyncio.create_task(brevo_service.remove_newsletter_contact(email))

    # Toujours 200 pour ne pas révéler si l'email existait
    return {"status": "unsubscribed"}
