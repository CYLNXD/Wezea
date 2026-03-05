
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.limiter import limiter
from app.models import ScanHistory

router = APIRouter(prefix="/public", tags=["public"])

# ── Score colors ───────────────────────────────────────────────────────────────
_SCORE_COLORS = {
    "low":      ("#16a34a", "#bbf7d0"),  # green — 80-100
    "moderate": ("#d97706", "#fef3c7"),  # amber — 60-79
    "high":     ("#ea580c", "#ffedd5"),  # orange — 40-59
    "critical": ("#dc2626", "#fee2e2"),  # red — 0-39
}

def _score_color(score: int) -> tuple[str, str]:
    if score >= 80:
        return _SCORE_COLORS["low"]
    if score >= 60:
        return _SCORE_COLORS["moderate"]
    if score >= 40:
        return _SCORE_COLORS["high"]
    return _SCORE_COLORS["critical"]


@router.get(
    "/badge/{domain}",
    summary     = "Badge SVG de sécurité (dynamique)",
    description = "Retourne un badge SVG avec le dernier score de sécurité connu pour un domaine.",
    responses   = {200: {"content": {"image/svg+xml": {}}}},
)
@limiter.limit("120/minute")
def security_badge(request: Request, domain: str, db: Session = Depends(get_db)):
    """
    Badge intégrable dans un README, un site ou un email.
    Exemple : <img src="https://scan.wezea.net/public/badge/example.com" />
    Retourne le dernier score connu — ou "?" si jamais scanné.
    Cache-Control: 1 heure (le badge change peu souvent).
    """
    domain = domain.lower().strip().lstrip("www.")

    last = (
        db.query(ScanHistory)
        .filter(ScanHistory.domain == domain)
        .order_by(ScanHistory.created_at.desc())
        .first()
    )

    if last:
        score     = last.security_score
        label     = str(score)
        fg, bg    = _score_color(score)
    else:
        score     = -1
        label     = "?"
        fg, bg    = "#64748b", "#1e293b"

    # Label width : 2 chars ~28px, 3 chars ~36px
    score_w = 28 if len(label) <= 2 else 36
    total_w = 108 + score_w

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="20">
  <defs>
    <linearGradient id="b" x2="0" y2="100%">
      <stop offset="0"   stop-color="#bbb" stop-opacity=".1"/>
      <stop offset="1"   stop-opacity=".1"/>
    </linearGradient>
    <clipPath id="r"><rect width="{total_w}" height="20" rx="4"/></clipPath>
  </defs>
  <g clip-path="url(#r)">
    <rect width="108"      height="20" fill="#1e293b"/>
    <rect x="108" width="{score_w}" height="20" fill="{fg}"/>
    <rect width="{total_w}" height="20" fill="url(#b)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="54" y="15" fill="#000" fill-opacity=".3">wezea security</text>
    <text x="54" y="14">wezea security</text>
    <text x="{108 + score_w // 2}" y="15" fill="#000" fill-opacity=".3" font-weight="bold">{label}</text>
    <text x="{108 + score_w // 2}" y="14" font-weight="bold">{label}</text>
  </g>
</svg>"""

    return Response(
        content      = svg,
        media_type   = "image/svg+xml",
        headers      = {
            "Cache-Control": "public, max-age=3600",
            "X-Score":       str(score),
        },
    )


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
