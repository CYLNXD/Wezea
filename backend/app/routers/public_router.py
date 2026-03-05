
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.limiter import limiter
from app.models import ScanHistory

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/stats", summary="Statistiques publiques")
@limiter.limit("60/minute")
def public_stats(request: Request, db: Session = Depends(get_db)):
    """
    Retourne des statistiques anonymisées pour la landing page.
    Aucune authentification requise.
    """
    total_scans = db.query(func.count(ScanHistory.id)).scalar() or 0

    # Nombre de vulnérabilités détectées (findings cumulés)
    # Approximation : moyenne ~4 findings par scan
    estimated_vulns = total_scans * 4

    return {
        "total_scans":      total_scans,
        "estimated_vulns":  estimated_vulns,
    }
