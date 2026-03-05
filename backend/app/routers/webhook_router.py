"""
CyberHealth Scanner — Webhook Router
=====================================
Webhooks sortants Pro : envoi automatique des résultats de scan
vers une URL externe (Zapier, Slack, CI/CD, etc.).

GET    /webhooks             → lister les webhooks actifs
POST   /webhooks             → créer un webhook (max 5 par compte)
DELETE /webhooks/{id}        → supprimer un webhook
POST   /webhooks/{id}/test   → envoyer un payload de test

Sécurité : chaque payload est signé HMAC-SHA256 via X-Wezea-Signature.
"""

from __future__ import annotations

import hashlib
import hmac
import json as _json
import secrets
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Webhook
from app.routers.auth_router import get_current_user

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

WEBHOOK_LIMIT_PRO = 5

ALLOWED_EVENTS = {
    "scan.completed",   # scan manuel terminé (POST /scan)
    "alert.triggered",  # alerte monitoring déclenchée
    "score.dropped",    # score en baisse de N points
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_pro(user: User) -> None:
    if user.plan not in ("pro",):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error":       "Les webhooks sont réservés au plan Pro.",
                "upgrade_url": "/upgrade",
            },
        )


def _sign_payload(secret: str, body: bytes) -> str:
    """Retourne 'sha256=<hex>' — compatible GitHub-style webhook signatures."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ── Schemas ───────────────────────────────────────────────────────────────────

class WebhookCreate(BaseModel):
    url:    str
    secret: str | None = None
    events: list[str]  = ["scan.completed", "alert.triggered"]


class WebhookResponse(BaseModel):
    id:           int
    url:          str
    events:       list[str]
    is_active:    bool
    created_at:   str
    last_fired_at: str | None
    last_status:  int | None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[WebhookResponse])
def list_webhooks(
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Liste les webhooks actifs du compte."""
    _require_pro(current_user)
    hooks = (
        db.query(Webhook)
        .filter(Webhook.user_id == current_user.id, Webhook.is_active == True)
        .order_by(Webhook.created_at.desc())
        .all()
    )
    return [
        WebhookResponse(
            id            = h.id,
            url           = h.url,
            events        = _json.loads(h.events) if h.events else [],
            is_active     = h.is_active,
            created_at    = h.created_at.isoformat(),
            last_fired_at = h.last_fired_at.isoformat() if h.last_fired_at else None,
            last_status   = h.last_status,
        )
        for h in hooks
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_webhook(
    body:         WebhookCreate,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Crée un webhook. Le secret est retourné une seule fois — conservez-le."""
    _require_pro(current_user)

    # Validation URL
    url = body.url.strip()
    if not url.startswith(("https://", "http://")):
        raise HTTPException(status_code=422, detail="L'URL doit commencer par http:// ou https://")
    if len(url) > 512:
        raise HTTPException(status_code=422, detail="URL trop longue (max 512 caractères).")

    # Validation events
    invalid = set(body.events) - ALLOWED_EVENTS
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Événements invalides : {', '.join(sorted(invalid))}. "
                   f"Valeurs acceptées : {', '.join(sorted(ALLOWED_EVENTS))}",
        )
    if not body.events:
        raise HTTPException(status_code=422, detail="Spécifiez au moins un événement.")

    # Limite par compte
    count = db.query(Webhook).filter(
        Webhook.user_id   == current_user.id,
        Webhook.is_active == True,
    ).count()
    if count >= WEBHOOK_LIMIT_PRO:
        raise HTTPException(
            status_code=429,
            detail={"error": f"Limite atteinte ({WEBHOOK_LIMIT_PRO} webhooks max par compte Pro)."},
        )

    secret = body.secret.strip() if body.secret else secrets.token_hex(32)

    hook = Webhook(
        user_id   = current_user.id,
        url       = url,
        secret    = secret,
        events    = _json.dumps(body.events),
        is_active = True,
    )
    db.add(hook)
    db.commit()
    db.refresh(hook)

    return {
        "id":      hook.id,
        "url":     hook.url,
        "secret":  secret,   # retourné UNE SEULE FOIS
        "events":  body.events,
        "message": "Webhook créé. Conservez le secret — il ne sera plus affiché.",
    }


@router.delete("/{webhook_id}", status_code=status.HTTP_200_OK)
def delete_webhook(
    webhook_id:   int,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Supprime (désactive) un webhook."""
    _require_pro(current_user)
    hook = db.query(Webhook).filter(
        Webhook.id      == webhook_id,
        Webhook.user_id == current_user.id,
    ).first()
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook introuvable.")
    hook.is_active = False
    db.commit()
    return {"message": "Webhook supprimé."}


@router.post("/{webhook_id}/test")
async def test_webhook(
    webhook_id:   int,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Envoie un payload de test à l'URL du webhook."""
    _require_pro(current_user)
    hook = db.query(Webhook).filter(
        Webhook.id        == webhook_id,
        Webhook.user_id   == current_user.id,
        Webhook.is_active == True,
    ).first()
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook introuvable.")

    payload = {
        "event":     "test",
        "timestamp": int(time.time()),
        "data": {
            "domain":         "example.com",
            "security_score": 72,
            "risk_level":     "MODERATE",
            "message":        "Ceci est un payload de test Wezea Security Scanner.",
        },
    }
    http_status = await _deliver(hook, payload, db)
    return {
        "delivered": 200 <= http_status < 400,
        "status":    http_status,
        "url":       hook.url,
    }


# ── Delivery engine ───────────────────────────────────────────────────────────

async def _deliver(hook: Webhook, payload: dict, db) -> int:
    """Envoie le payload et met à jour last_fired_at / last_status en DB."""
    body = _json.dumps(payload).encode()
    headers = {
        "Content-Type":    "application/json",
        "User-Agent":      "Wezea-Scanner/1.0",
        "X-Wezea-Event":   payload.get("event", "unknown"),
        "X-Wezea-Delivery": secrets.token_hex(8),
    }
    if hook.secret:
        headers["X-Wezea-Signature"] = _sign_payload(hook.secret, body)

    http_status = 0
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(hook.url, content=body, headers=headers)
            http_status = resp.status_code
    except Exception:
        http_status = 0  # timeout / connexion refusée

    hook.last_fired_at = datetime.now(timezone.utc)
    hook.last_status   = http_status
    db.commit()
    return http_status


async def fire_webhooks(user_id: int, event: str, payload: dict, db) -> None:
    """
    Déclenche tous les webhooks actifs d'un utilisateur pour un événement.
    Silencieux en cas d'erreur — ne doit jamais bloquer le flux principal.
    """
    hooks = (
        db.query(Webhook)
        .filter(Webhook.user_id == user_id, Webhook.is_active == True)
        .all()
    )
    for hook in hooks:
        events = _json.loads(hook.events) if hook.events else []
        if event in events:
            try:
                await _deliver(hook, {"event": event, "timestamp": int(time.time()), **payload}, db)
            except Exception:
                pass  # silencieux — ne pas bloquer le scan
