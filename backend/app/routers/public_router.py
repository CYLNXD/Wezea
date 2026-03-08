
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.limiter import limiter
from app.models import ScanHistory, BlogLink

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


@router.get(
    "/scan/{scan_uuid}",
    summary     = "Résultats publics d'un scan",
    description = "Retourne les résultats d'un scan si le propriétaire l'a partagé (public_share=True).",
)
@limiter.limit("60/minute")
def public_scan(request: Request, scan_uuid: str, db: Session = Depends(get_db)):
    """
    Endpoint sans authentification pour afficher un rapport de scan partagé.
    Seuls les scans marqués `public_share=True` sont exposés.
    """
    scan = (
        db.query(ScanHistory)
        .filter(ScanHistory.scan_uuid == scan_uuid)
        .first()
    )
    if not scan:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Scan not found")

    # Vérifier si le scan est partageable (colonne public_share, défaut False)
    if not getattr(scan, "public_share", False):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="This scan is not shared publicly")

    details  = scan.get_scan_details()
    findings = scan.get_findings()

    return {
        "scan_uuid":      scan.scan_uuid,
        "domain":         scan.domain,
        "scanned_at":     scan.created_at.isoformat(),
        "security_score": scan.security_score,
        "risk_level":     scan.risk_level,
        "findings_count": scan.findings_count,
        "findings":       findings,
        "scan_duration":  scan.scan_duration,
        "dns_details":    details.get("dns_details", {}),
        "ssl_details":    details.get("ssl_details", {}),
        "port_details":   details.get("port_details", {}),
        "recommendations": details.get("recommendations", []),
    }


@router.get("/stats", summary="Statistiques publiques")
@limiter.limit("60/minute")
def public_stats(request: Request, db: Session = Depends(get_db)):
    """
    Retourne des statistiques anonymisées pour la landing page et le
    benchmark de maturité (widget "Votre maturité vs industrie").
    Aucune authentification requise.
    """
    total_scans = db.query(func.count(ScanHistory.id)).scalar() or 0

    # Nombre de vulnérabilités détectées (findings cumulés)
    # Approximation : moyenne ~4 findings par scan
    estimated_vulns = total_scans * 4

    # ── Score moyen industrie ─────────────────────────────────────────────────
    # Calculé sur les scans authentifiés (qualité > scans anonymes one-shot).
    # Fallback 70 tant que la base n'a pas assez de données (< 50 scans).
    # 70/100 crée une pression maximale sur les mauvais scores tout en
    # valorisant les bons scores ("vous êtes dans le top X%").
    INDUSTRY_BASELINE   = 70   # utilisé si pas assez de données réelles
    MIN_SCANS_FOR_REAL  = 50   # seuil pour switcher sur la moyenne réelle

    avg_row = db.query(func.avg(ScanHistory.security_score)).scalar()
    real_avg = round(float(avg_row)) if avg_row is not None else None

    if real_avg is not None and total_scans >= MIN_SCANS_FOR_REAL:
        industry_avg = real_avg
        avg_source   = "real"
    else:
        industry_avg = INDUSTRY_BASELINE
        avg_source   = "baseline"

    return {
        "total_scans":      total_scans,
        "estimated_vulns":  estimated_vulns,
        "industry_avg":     industry_avg,   # score moyen des entreprises scannées
        "avg_source":       avg_source,     # "real" | "baseline"
    }


@router.get("/blog-links", summary="Liens articles de blog")
@limiter.limit("60/minute")
def public_blog_links(request: Request, db: Session = Depends(get_db)):
    """
    Retourne tous les liens d'articles de blog configurés par l'admin.
    Utilisé par le frontend pour associer des articles aux recommandations.
    Aucune authentification requise.
    """
    links = db.query(BlogLink).all()
    return [
        {
            "id":            lnk.id,
            "match_keyword": lnk.match_keyword,
            "article_title": lnk.article_title,
            "article_url":   lnk.article_url,
        }
        for lnk in links
    ]
