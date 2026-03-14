"""
Compliance Router — Rapport NIS2/RGPD actionable
=================================================
GET   /compliance/report?domain=X&lang=fr   → Rapport combiné tech + org + progress
GET   /compliance/checklist?domain=X        → Items checklist avec état (Starter+)
PATCH /compliance/checklist                 → Toggle item (Starter+)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.compliance_mapper import (
    COMPLIANCE_CRITERIA,
    ORGANIZATIONAL_ITEMS,
    ComplianceMapper,
)
from app.database import get_db
from app.models import ComplianceChecklist, ScanHistory, User
from app.routers.auth_router import get_current_user, get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compliance", tags=["compliance"])

_PAID_PLANS = ("starter", "pro", "dev")

_mapper = ComplianceMapper()


# ── Helpers ─────────────────────────────────────────────────────────────────────


def _require_paid(user: User) -> None:
    if user.plan not in _PAID_PLANS:
        raise HTTPException(status_code=403, detail="Starter plan or above required")


def _get_latest_scan(domain: str, user_id: int, db: Session) -> Optional[ScanHistory]:
    """Dernier scan pour ce domaine et cet utilisateur."""
    return (
        db.query(ScanHistory)
        .filter(ScanHistory.user_id == user_id, ScanHistory.domain == domain)
        .order_by(ScanHistory.created_at.desc())
        .first()
    )


def _parse_findings(scan: ScanHistory) -> list[dict]:
    """Extrait les findings du scan_details_json."""
    if not scan or not scan.scan_details_json:
        return []
    try:
        data = json.loads(scan.scan_details_json)
        return data.get("findings", [])
    except (json.JSONDecodeError, TypeError):
        return []


# ── GET /compliance/report ──────────────────────────────────────────────────────


@router.get("/report")
def get_compliance_report(
    domain: str = Query(..., min_length=1),
    lang: str = Query("fr", pattern="^(fr|en)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rapport de conformité combiné : critères techniques (depuis scan) + items organisationnels."""
    scan = _get_latest_scan(domain, current_user.id, db)
    findings = _parse_findings(scan)

    # Évaluation technique via ComplianceMapper
    compliance = _mapper.analyze(findings)
    result = compliance.to_dict()

    # Ajouter les items organisationnels avec état utilisateur
    checklist_items = (
        db.query(ComplianceChecklist)
        .filter(
            ComplianceChecklist.user_id == current_user.id,
            ComplianceChecklist.domain == domain,
        )
        .all()
    )
    checked_map = {c.item_id: {"checked": c.checked, "notes": c.notes or ""} for c in checklist_items}

    org_items = []
    for item in ORGANIZATIONAL_ITEMS:
        state = checked_map.get(item["id"], {"checked": False, "notes": ""})
        org_items.append({
            "id": item["id"],
            "label": item[f"label_{lang}"] if lang in ("fr", "en") else item["label_fr"],
            "description": item[f"desc_{lang}"] if lang in ("fr", "en") else item["desc_fr"],
            "nis2_articles": item["nis2_articles"],
            "rgpd_articles": item["rgpd_articles"],
            "checked": state["checked"],
            "notes": state["notes"],
        })

    # Progress counters
    tech_total = len([c for c in result.get("criteria", []) if c["status"] != "not_assessable"])
    tech_pass = len([c for c in result.get("criteria", []) if c["status"] == "pass"])
    org_total = len(ORGANIZATIONAL_ITEMS)
    org_pass = len([i for i in org_items if i["checked"]])

    result["organizational_items"] = org_items
    result["progress"] = {
        "tech_total": tech_total,
        "tech_pass": tech_pass,
        "org_total": org_total,
        "org_pass": org_pass,
        "total": tech_total + org_total,
        "completed": tech_pass + org_pass,
    }
    result["domain"] = domain
    result["has_scan"] = scan is not None

    return result


# ── GET /compliance/checklist ───────────────────────────────────────────────────


@router.get("/checklist")
def get_checklist(
    domain: str = Query(..., min_length=1),
    lang: str = Query("fr", pattern="^(fr|en)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retourne les items organisationnels avec leur état pour l'utilisateur."""
    _require_paid(current_user)

    checklist_items = (
        db.query(ComplianceChecklist)
        .filter(
            ComplianceChecklist.user_id == current_user.id,
            ComplianceChecklist.domain == domain,
        )
        .all()
    )
    checked_map = {c.item_id: {"checked": c.checked, "notes": c.notes or "", "checked_at": c.checked_at} for c in checklist_items}

    items = []
    for item in ORGANIZATIONAL_ITEMS:
        state = checked_map.get(item["id"], {"checked": False, "notes": "", "checked_at": None})
        items.append({
            "id": item["id"],
            "label": item[f"label_{lang}"] if lang in ("fr", "en") else item["label_fr"],
            "description": item[f"desc_{lang}"] if lang in ("fr", "en") else item["desc_fr"],
            "nis2_articles": item["nis2_articles"],
            "rgpd_articles": item["rgpd_articles"],
            "checked": state["checked"],
            "notes": state["notes"],
            "checked_at": state["checked_at"].isoformat() if state["checked_at"] else None,
        })

    return {"domain": domain, "items": items}


# ── PATCH /compliance/checklist ─────────────────────────────────────────────────


class ChecklistToggle(BaseModel):
    domain: str
    item_id: str
    checked: bool
    notes: str = ""


@router.patch("/checklist")
def toggle_checklist_item(
    body: ChecklistToggle,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Toggle un item de la checklist organisationnelle (upsert)."""
    _require_paid(current_user)

    # Valider que l'item_id existe
    valid_ids = {item["id"] for item in ORGANIZATIONAL_ITEMS}
    if body.item_id not in valid_ids:
        raise HTTPException(status_code=400, detail=f"Unknown item_id: {body.item_id}")

    # Upsert
    existing = (
        db.query(ComplianceChecklist)
        .filter(
            ComplianceChecklist.user_id == current_user.id,
            ComplianceChecklist.domain == body.domain,
            ComplianceChecklist.item_id == body.item_id,
        )
        .first()
    )

    now = datetime.now(timezone.utc)

    if existing:
        existing.checked = body.checked
        existing.notes = body.notes
        existing.checked_at = now if body.checked else None
        existing.updated_at = now
    else:
        item = ComplianceChecklist(
            user_id=current_user.id,
            domain=body.domain,
            item_id=body.item_id,
            checked=body.checked,
            notes=body.notes,
            checked_at=now if body.checked else None,
        )
        db.add(item)

    db.commit()

    return {"status": "ok", "item_id": body.item_id, "checked": body.checked}
