"""
Contact Router — Formulaire de support
"""
import asyncio
import os
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.limiter import limiter
from app.models import ContactMessage
from app.routers.auth_router import get_optional_user
from app.models import User
from app.services import brevo_service

router = APIRouter(prefix="/contact", tags=["Contact"])

SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "support@wezea.net")

SUBJECTS = [
    "Question sur mon compte",
    "Problème technique",
    "Question sur les tarifs / offres",
    "Demande de démo",
    "Signaler un bug",
    "Autre",
]


class ContactRequest(BaseModel):
    name:    str
    email:   str
    subject: str
    message: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Le nom doit contenir au moins 2 caractères.")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Adresse email invalide.")
        return v

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("Le message doit contenir au moins 10 caractères.")
        if len(v) > 5000:
            raise ValueError("Le message est trop long (max 5000 caractères).")
        return v

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, v: str) -> str:
        v = v.strip()
        if v not in SUBJECTS:
            raise ValueError(
                f"Sujet invalide. Valeurs acceptées : {', '.join(SUBJECTS)}"
            )
        return v


FRONTEND_URL = os.getenv("FRONTEND_URL", "https://scan.wezea.net")


@router.get("", include_in_schema=False)
def contact_redirect():
    """Redirige vers la page de contact du frontend (lien depuis le PDF)."""
    return RedirectResponse(url=f"{FRONTEND_URL}?page=contact", status_code=302)


@router.get("/subjects")
def get_subjects():
    """Retourne la liste des sujets disponibles."""
    return {"subjects": SUBJECTS}


@router.post("", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")
async def submit_contact(
    request: Request,
    body: ContactRequest,
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Enregistre le message de contact et envoie les emails de notification."""

    # Sauvegarder en DB
    msg = ContactMessage(
        name    = body.name,
        email   = body.email,
        subject = body.subject,
        message = body.message,
        user_id = current_user.id if current_user else None,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # Envois email en arrière-plan
    asyncio.create_task(brevo_service.send_contact_notification(
        name    = body.name,
        email   = body.email,
        subject = body.subject,
        message = body.message,
        msg_id  = msg.id,
    ))
    asyncio.create_task(brevo_service.send_contact_confirmation(
        name    = body.name,
        email   = body.email,
        subject = body.subject,
    ))

    return {
        "id":      msg.id,
        "status":  "received",
        "message": "Votre message a bien été reçu. Nous vous répondrons dans les plus brefs délais.",
    }
