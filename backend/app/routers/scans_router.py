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
