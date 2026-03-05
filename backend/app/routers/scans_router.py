"""
Scans Router — History, detail, delete
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ScanHistory
from app.routers.auth_router import get_current_user
from app.models import User

router = APIRouter(prefix="/scans", tags=["scans"])


@router.get("/history")
def get_history(
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Borner limit pour éviter un OOM sur de très grands historiques
    limit  = max(1, min(limit, 100))
    offset = max(0, offset)

    total = db.query(ScanHistory).filter(ScanHistory.user_id == current_user.id).count()
    scans = (
        db.query(ScanHistory)
        .filter(ScanHistory.user_id == current_user.id)
        .order_by(ScanHistory.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "scans": [
            {
                "id": s.id,
                "scan_uuid": s.scan_uuid,
                "domain": s.domain,
                "security_score": s.security_score,
                "risk_level": s.risk_level,
                "findings_count": s.findings_count,
                "scan_duration": s.scan_duration,
                "created_at": s.created_at.isoformat(),
            }
            for s in scans
        ],
    }


@router.get("/history/{scan_uuid}")
def get_scan_detail(
    scan_uuid: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scan = (
        db.query(ScanHistory)
        .filter(
            ScanHistory.scan_uuid == scan_uuid,
            ScanHistory.user_id == current_user.id,
        )
        .first()
    )
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    details = scan.get_scan_details()
    return {
        "id": scan.id,
        "scan_uuid": scan.scan_uuid,
        "domain": scan.domain,
        "security_score": scan.security_score,
        "risk_level": scan.risk_level,
        "findings_count": scan.findings_count,
        "findings": scan.get_findings(),
        "scan_duration": scan.scan_duration,
        "created_at": scan.created_at.isoformat(),
        # Champs pour la génération PDF (persistés depuis la v2)
        "dns_details":       details.get("dns_details", {}),
        "ssl_details":       details.get("ssl_details", {}),
        "port_details":      details.get("port_details", {}),
        "recommendations":   details.get("recommendations", []),
        "subdomain_details": details.get("subdomain_details", {}),
        "vuln_details":      details.get("vuln_details", {}),
    }


@router.delete("/history/{scan_uuid}", status_code=204)
def delete_scan(
    scan_uuid: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scan = (
        db.query(ScanHistory)
        .filter(
            ScanHistory.scan_uuid == scan_uuid,
            ScanHistory.user_id == current_user.id,
        )
        .first()
    )
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    db.delete(scan)
    db.commit()
