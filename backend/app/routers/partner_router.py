"""
Partner Router — Programme partenaire Wezea
============================================
Endpoints publics :
    POST /partners              → Inscription partenaire (formulaire public)

Endpoints admin :
    GET    /partners/admin       → Liste des partenaires
    POST   /partners/admin/{id}/activate → Activer un partenaire (+ essai Pro 30j)
    POST   /partners/admin/{id}/reject   → Rejeter une candidature
"""

import asyncio
import logging
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Partner, User
from app.routers.admin_router import require_admin
from app.limiter import limiter

logger = logging.getLogger("cyberhealth.partners")

router = APIRouter(prefix="/partners", tags=["partners"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class PartnerRegisterRequest(BaseModel):
    first_name: str
    email: str
    company: str
    website: Optional[str] = None
    client_count: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Email invalide")
        return v

    @field_validator("first_name", "company")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Ce champ est requis")
        return v.strip()


class PartnerView(BaseModel):
    id: int
    first_name: str
    email: str
    company: str
    website: Optional[str]
    client_count: Optional[str]
    status: str
    referral_code: str
    referral_count: int
    notes: Optional[str]
    created_at: str
    activated_at: Optional[str]
    pro_trial_ends: Optional[str]

    model_config = {"from_attributes": True}


class PartnerAdminAction(BaseModel):
    notes: Optional[str] = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _generate_referral_code() -> str:
    """Génère un code partenaire unique au format wza_XXXXXX."""
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(chars) for _ in range(6))
    return f"wza_{suffix}"


def _partner_to_view(p: Partner) -> PartnerView:
    return PartnerView(
        id=p.id,
        first_name=p.first_name,
        email=p.email,
        company=p.company,
        website=p.website,
        client_count=p.client_count,
        status=p.status,
        referral_code=p.referral_code,
        referral_count=p.referral_count,
        notes=p.notes,
        created_at=p.created_at.isoformat() if p.created_at else "",
        activated_at=p.activated_at.isoformat() if p.activated_at else None,
        pro_trial_ends=p.pro_trial_ends.isoformat() if p.pro_trial_ends else None,
    )


# ─── Endpoints publics ───────────────────────────────────────────────────────

@router.post("", status_code=201)
async def register_partner(
    body: PartnerRegisterRequest,
    db: Session = Depends(get_db),
):
    """Inscription partenaire — formulaire public."""
    # Vérifier qu'un partenaire avec cet email n'existe pas déjà
    existing = db.query(Partner).filter(Partner.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Un partenaire avec cet email existe déjà.",
        )

    # Générer un code referral unique
    code = _generate_referral_code()
    while db.query(Partner).filter(Partner.referral_code == code).first():
        code = _generate_referral_code()

    partner = Partner(
        first_name=body.first_name,
        email=body.email,
        company=body.company,
        website=body.website,
        client_count=body.client_count,
        referral_code=code,
    )
    db.add(partner)
    db.commit()
    db.refresh(partner)

    # Notification admin (non bloquant)
    try:
        from app.services.brevo_service import send_partner_application_notification
        asyncio.create_task(
            send_partner_application_notification(body.email, body.first_name, body.company)
        )
    except Exception as e:
        logger.warning("Erreur notification partenaire : %s", e)

    return {"status": "ok", "message": "Candidature enregistrée. Nous vous recontacterons rapidement."}


# ─── Endpoints admin ──────────────────────────────────────────────────────────

@router.get("/admin", response_model=List[PartnerView])
def list_partners(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Liste tous les partenaires (admin only)."""
    partners = db.query(Partner).order_by(Partner.created_at.desc()).all()
    return [_partner_to_view(p) for p in partners]


@router.post("/admin/{partner_id}/activate", response_model=PartnerView)
async def activate_partner(
    partner_id: int,
    body: PartnerAdminAction = PartnerAdminAction(),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Active un partenaire + lui accorde un essai Pro de 30 jours."""
    partner = db.query(Partner).filter(Partner.id == partner_id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Partenaire introuvable")

    now = datetime.now(timezone.utc)
    partner.status = "active"
    partner.activated_at = now
    partner.pro_trial_ends = now + timedelta(days=30)
    if body.notes:
        partner.notes = body.notes

    # Si un compte utilisateur existe avec cet email, upgrader en Pro
    user = db.query(User).filter(User.email == partner.email).first()
    if user and user.plan == "free":
        user.plan = "pro"
        user.subscription_status = "active"

    db.commit()
    db.refresh(partner)

    # Email de confirmation au partenaire (non bloquant)
    try:
        from app.services.brevo_service import send_partner_activated_email
        asyncio.create_task(
            send_partner_activated_email(partner.email, partner.first_name, partner.referral_code)
        )
    except Exception as e:
        logger.warning("Erreur email activation partenaire : %s", e)

    return _partner_to_view(partner)


@router.post("/admin/{partner_id}/reject", response_model=PartnerView)
def reject_partner(
    partner_id: int,
    body: PartnerAdminAction = PartnerAdminAction(),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Rejette une candidature partenaire."""
    partner = db.query(Partner).filter(Partner.id == partner_id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Partenaire introuvable")

    partner.status = "rejected"
    if body.notes:
        partner.notes = body.notes

    db.commit()
    db.refresh(partner)
    return _partner_to_view(partner)
