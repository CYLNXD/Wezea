"""
Remediation Router — Guides de remédiation pas-à-pas
=====================================================
GET  /remediation/guide?title=X&lang=fr   → Guide pour un finding
POST /remediation/guides                  → Batch lookup
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.remediation_guides import (
    RemediationGuide,
    get_guide_for_finding,
    get_guides_for_findings,
)
from app.routers.auth_router import get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/remediation", tags=["remediation"])


# ── Helpers ─────────────────────────────────────────────────────────────────────

_PAID_PLANS = ("starter", "pro", "dev")


def _serialize_guide(
    guide: RemediationGuide,
    lang: str = "fr",
    user: Optional[User] = None,
) -> dict:
    """Sérialise un guide, avec paywall si premium et user free/anon."""
    is_locked = guide.is_premium and (user is None or user.plan not in _PAID_PLANS)
    title = guide.title_fr if lang == "fr" else guide.title_en

    result: dict = {
        "key": guide.key,
        "title": title,
        "difficulty": guide.difficulty,
        "estimated_time_min": guide.estimated_time_min,
        "step_count": len(guide.steps),
        "is_premium": guide.is_premium,
        "locked": is_locked,
    }

    if is_locked:
        # Free users: résumé seulement, pas de détail des étapes
        result["steps"] = []
    else:
        result["steps"] = [
            {
                "order": s.order,
                "action": s.action_fr if lang == "fr" else s.action_en,
                "where": s.where_fr if lang == "fr" else s.where_en,
                "verify": s.verify_fr if lang == "fr" else s.verify_en,
            }
            for s in guide.steps
        ]

    return result


# ── Endpoints ───────────────────────────────────────────────────────────────────


@router.get("/guide")
def get_guide(
    title: str = Query(..., min_length=1, description="Titre du finding"),
    lang: str = Query("fr", pattern="^(fr|en)$"),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Retourne le guide de remédiation pour un finding donné."""
    guide = get_guide_for_finding(title)
    if guide is None:
        raise HTTPException(status_code=404, detail="No guide found for this finding")
    return _serialize_guide(guide, lang=lang, user=current_user)


class BatchRequest(BaseModel):
    titles: list[str]
    lang: str = "fr"


@router.post("/guides")
def get_guides_batch(
    body: BatchRequest,
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Retourne les guides pour une liste de titres (batch)."""
    lang = body.lang if body.lang in ("fr", "en") else "fr"
    results = get_guides_for_findings(body.titles)
    return {
        title: _serialize_guide(guide, lang=lang, user=current_user) if guide else None
        for title, guide in results.items()
    }
