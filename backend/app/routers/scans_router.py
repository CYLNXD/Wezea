"""
Scans Router — History, detail, delete, export (JSON / CSV / PDF)
"""

import asyncio
import csv
import io
import json as _json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ScanHistory
from app.routers.auth_router import get_current_user
from app.models import User

logger = logging.getLogger(__name__)

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
                "public_share": bool(s.public_share),
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


@router.get("/history/{scan_uuid}/export")
async def export_scan(
    scan_uuid:    str,
    format:       str = Query("json", pattern="^(json|csv|pdf)$"),
    lang:         str = Query("fr",   pattern="^(fr|en)$"),
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Exporte un scan en JSON, CSV ou PDF.
    GET /scans/history/{uuid}/export?format=json
    GET /scans/history/{uuid}/export?format=csv
    GET /scans/history/{uuid}/export?format=pdf&lang=fr
    """
    scan = (
        db.query(ScanHistory)
        .filter(ScanHistory.scan_uuid == scan_uuid, ScanHistory.user_id == current_user.id)
        .first()
    )
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    details  = scan.get_scan_details()
    findings = scan.get_findings()
    filename_base = f"wezea-scan-{scan.domain}-{scan.created_at.strftime('%Y%m%d')}"

    if format == "json":
        data = {
            "scan_uuid":      scan.scan_uuid,
            "domain":         scan.domain,
            "scanned_at":     scan.created_at.isoformat(),
            "security_score": scan.security_score,
            "risk_level":     scan.risk_level,
            "findings":       findings,
            "dns_details":    details.get("dns_details", {}),
            "ssl_details":    details.get("ssl_details", {}),
            "port_details":   details.get("port_details", {}),
            "recommendations": details.get("recommendations", []),
        }
        return Response(
            content     = _json.dumps(data, ensure_ascii=False, indent=2),
            media_type  = "application/json",
            headers     = {"Content-Disposition": f'attachment; filename="{filename_base}.json"'},
        )

    if format == "csv":
        # Une ligne par finding
        output  = io.StringIO()
        writer  = csv.writer(output)
        writer.writerow(["domain", "scanned_at", "security_score", "risk_level",
                         "finding_title", "category", "severity", "penalty",
                         "plain_explanation", "recommendation", "technical_detail"])
        for f in findings:
            writer.writerow([
                scan.domain,
                scan.created_at.isoformat(),
                scan.security_score,
                scan.risk_level,
                f.get("title", ""),
                f.get("category", ""),
                f.get("severity", ""),
                f.get("penalty", ""),
                f.get("plain_explanation", ""),
                f.get("recommendation", ""),
                f.get("technical_detail", ""),
            ])
        return Response(
            content     = output.getvalue(),
            media_type  = "text/csv; charset=utf-8",
            headers     = {"Content-Disposition": f'attachment; filename="{filename_base}.csv"'},
        )

    # ── PDF ────────────────────────────────────────────────────────────────────
    from app.services import report_service  # import local — évite le chargement au démarrage

    audit_data = {
        "scan_id":           scan.scan_uuid,
        "domain":            scan.domain,
        "scanned_at":        scan.created_at.isoformat(),
        "security_score":    scan.security_score,
        "risk_level":        scan.risk_level,
        "findings":          findings,
        "dns_details":       details.get("dns_details", {}),
        "ssl_details":       details.get("ssl_details", {}),
        "port_details":      details.get("port_details", {}),
        "recommendations":   details.get("recommendations", []),
        "scan_duration_ms":  int(getattr(scan, "scan_duration", 0) or 0),
        "subdomain_details": details.get("subdomain_details", {}),
        "vuln_details":      details.get("vuln_details", {}),
    }

    # White-label si utilisateur Pro
    white_label = None
    if (
        current_user.plan == "pro"
        and getattr(current_user, "wb_enabled", False)
        and getattr(current_user, "wb_company_name", None)
    ):
        white_label = {
            "enabled":       True,
            "company_name":  current_user.wb_company_name,
            "logo_b64":      getattr(current_user, "wb_logo_b64", None),
            "primary_color": getattr(current_user, "wb_primary_color", None),
        }

    brand = (
        current_user.wb_company_name.lower().replace(" ", "-")
        if white_label else "wezea"
    )
    filename_pdf = f"{brand}-report-{scan.domain}-{scan.created_at.strftime('%Y%m%d')}.pdf"

    try:
        loop      = asyncio.get_event_loop()
        pdf_bytes = await loop.run_in_executor(
            None,
            lambda: report_service.generate_pdf(audit_data, lang, white_label),
        )
    except RuntimeError as exc:
        logger.error("PDF generation error (RuntimeError): %s", exc)
        raise HTTPException(
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE,
            detail      = "Service de génération PDF indisponible.",
        ) from exc
    except Exception as exc:
        logger.error("PDF generation error (Exception): %s", exc)
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail      = "Erreur lors de la génération du rapport PDF.",
        ) from exc

    return Response(
        content    = pdf_bytes,
        media_type = "application/pdf",
        headers    = {
            "Content-Disposition": f'attachment; filename="{filename_pdf}"',
            "Content-Length":      str(len(pdf_bytes)),
        },
    )


@router.patch("/history/{scan_uuid}/share")
def toggle_share(
    scan_uuid:    str,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Active ou désactive le lien de partage public pour un scan."""
    scan = (
        db.query(ScanHistory)
        .filter(ScanHistory.scan_uuid == scan_uuid, ScanHistory.user_id == current_user.id)
        .first()
    )
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    scan.public_share = not scan.public_share
    db.commit()
    return {"scan_uuid": scan_uuid, "public_share": scan.public_share}


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
