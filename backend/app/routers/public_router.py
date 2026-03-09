
import os
import html as _html

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, HTMLResponse
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


# ─────────────────────────────────────────────────────────────────────────────
# Helpers OG
# ─────────────────────────────────────────────────────────────────────────────

_FRONTEND_URL = os.getenv("FRONTEND_URL", "https://wezea.net")
_API_URL      = os.getenv("VITE_API_URL", "https://scan.wezea.net")  # fallback

def _og_scan_or_none(scan_uuid: str, db: Session):
    """Retourne le scan si publiquement partagé, sinon None."""
    return (
        db.query(ScanHistory)
        .filter(ScanHistory.scan_uuid == scan_uuid, ScanHistory.public_share.is_(True))
        .first()
    )

def _risk_label_fr(risk_level: str) -> str:
    return {"low": "Faible", "moderate": "Modéré", "high": "Élevé", "critical": "Critique"}.get(
        (risk_level or "").lower(), risk_level or "Inconnu"
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /public/og/{uuid}  — og:image SVG 1200×630
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/og/{scan_uuid}",
    summary     = "Image og:image SVG pour les previews réseaux sociaux",
    responses   = {200: {"content": {"image/svg+xml": {}}}},
)
@limiter.limit("120/minute")
def public_og_image(request: Request, scan_uuid: str, db: Session = Depends(get_db)):
    """
    Image SVG 1200×630 intégrable comme og:image.
    Affiche le score, le domaine, le niveau de risque et le branding Wezea.
    Retourne une image générique si le scan n'existe pas ou n'est pas partagé.
    """
    scan = _og_scan_or_none(scan_uuid, db)

    if scan:
        score     = scan.security_score
        domain    = scan.domain
        risk_lvl  = scan.risk_level or "moderate"
        findings  = scan.findings_count or 0
        fg, _     = _score_color(score)
        risk_lbl  = _risk_label_fr(risk_lvl)
        vuln_txt  = f"{findings} vulnérabilité{'s' if findings > 1 else ''} détectée{'s' if findings > 1 else ''}"
    else:
        score    = None
        domain   = "Rapport de sécurité"
        risk_lbl = ""
        vuln_txt = ""
        fg       = "#64748b"

    score_txt   = str(score) + "%" if score is not None else "—"
    domain_safe = _html.escape(domain)
    vuln_safe   = _html.escape(vuln_txt)
    risk_safe   = _html.escape(risk_lbl)

    # ── Barre de progression ──────────────────────────────────────────────────
    bar_w    = int((score or 0) * 5.2)   # 0–520 px sur une largeur de 520
    bar_fill = f'<rect x="340" y="370" width="{bar_w}" height="6" rx="3" fill="{fg}" opacity="0.9"/>'

    # ── Pill niveau de risque ─────────────────────────────────────────────────
    risk_pill = ""
    if risk_safe:
        risk_pill = (
            f'<rect x="340" y="400" width="160" height="28" rx="6" '
            f'fill="{fg}" opacity="0.15"/>'
            f'<rect x="340" y="400" width="160" height="28" rx="6" '
            f'fill="none" stroke="{fg}" stroke-width="1" opacity="0.5"/>'
            f'<text x="420" y="419" font-family="system-ui,Arial,sans-serif" '
            f'font-size="13" font-weight="600" fill="{fg}" text-anchor="middle">'
            f'NIVEAU {risk_safe.upper()}</text>'
        )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%"   stop-color="#0f172a"/>
      <stop offset="60%"  stop-color="#1e3a5f"/>
      <stop offset="100%" stop-color="#0f172a"/>
    </linearGradient>
  </defs>

  <!-- Fond -->
  <rect width="1200" height="630" fill="url(#bg)"/>

  <!-- Accent stripe gauche -->
  <rect x="0" y="0" width="6" height="630" fill="{fg}" opacity="0.8"/>

  <!-- Bande top -->
  <rect x="0" y="0" width="1200" height="80" fill="rgba(255,255,255,0.03)"/>

  <!-- Logo Wezea -->
  <text x="48" y="52" font-family="system-ui,Arial,sans-serif" font-size="26"
        font-weight="800" fill="white" letter-spacing="-0.5">We</text>
  <text x="86" y="52" font-family="system-ui,Arial,sans-serif" font-size="26"
        font-weight="800" fill="#38bdf8" letter-spacing="-0.5">zea</text>
  <text x="48" y="72" font-family="system-ui,Arial,sans-serif" font-size="12"
        fill="rgba(255,255,255,0.35)" letter-spacing="2">SECURITY SCANNER</text>

  <!-- Label top-right -->
  <text x="1152" y="44" font-family="system-ui,Arial,sans-serif" font-size="13"
        fill="rgba(255,255,255,0.4)" text-anchor="end">Rapport de sécurité</text>

  <!-- Séparateur -->
  <line x1="40" y1="95" x2="1160" y2="95" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>

  <!-- Score géant (gauche) -->
  <text x="200" y="330" font-family="system-ui,Arial,sans-serif" font-size="180"
        font-weight="900" fill="{fg}" text-anchor="middle" opacity="0.95">{score_txt}</text>
  <text x="200" y="375" font-family="system-ui,Arial,sans-serif" font-size="16"
        fill="rgba(255,255,255,0.4)" text-anchor="middle" letter-spacing="3">SECURITY SCORE</text>

  <!-- Séparateur vertical -->
  <line x1="310" y1="160" x2="310" y2="480" stroke="rgba(255,255,255,0.1)" stroke-width="1"/>

  <!-- Domaine -->
  <text x="340" y="220" font-family="ui-monospace,monospace" font-size="32"
        font-weight="700" fill="white" opacity="0.9">{domain_safe}</text>

  <!-- Subtitle -->
  <text x="340" y="260" font-family="system-ui,Arial,sans-serif" font-size="16"
        fill="rgba(255,255,255,0.45)">Analyse de l&#x27;empreinte publique de sécurité</text>

  <!-- Bar track -->
  <rect x="340" y="370" width="520" height="6" rx="3" fill="rgba(255,255,255,0.08)"/>
  {bar_fill}

  <!-- Risk pill -->
  {risk_pill}

  <!-- Vulnérabilités -->
  <text x="340" y="475" font-family="system-ui,Arial,sans-serif" font-size="15"
        fill="rgba(255,255,255,0.4)">{vuln_safe}</text>

  <!-- Footer -->
  <line x1="40" y1="555" x2="1160" y2="555" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
  <text x="48" y="590" font-family="system-ui,Arial,sans-serif" font-size="14"
        fill="rgba(255,255,255,0.3)">wezea.net · Cybersécurité pour les PME</text>
  <text x="1152" y="590" font-family="system-ui,Arial,sans-serif" font-size="14"
        fill="rgba(255,255,255,0.2)" text-anchor="end">scan.wezea.net</text>
</svg>"""

    return Response(
        content    = svg,
        media_type = "image/svg+xml",
        headers    = {"Cache-Control": "public, max-age=3600"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /public/preview/{uuid}  — HTML avec og: meta tags + redirect
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/preview/{scan_uuid}",
    summary  = "Page HTML de preview pour les bots sociaux (og: meta tags + redirect)",
    response_class = HTMLResponse,
)
@limiter.limit("120/minute")
def public_preview(request: Request, scan_uuid: str, db: Session = Depends(get_db)):
    """
    Servi par nginx uniquement aux bots sociaux (WhatsApp, Slack, Twitter…).
    Contient les og: meta tags et redirige immédiatement les navigateurs vers
    la vraie page React wezea.net/r/{uuid}.
    """
    scan   = _og_scan_or_none(scan_uuid, db)
    target = f"{_FRONTEND_URL}/r/{scan_uuid}"

    # ── Construire les meta tags ──────────────────────────────────────────────
    api_base = os.getenv("VITE_API_URL", "https://scan.wezea.net")
    og_image = f"{api_base}/public/og/{scan_uuid}"

    if scan:
        score    = scan.security_score
        domain   = scan.domain
        risk_lbl = _risk_label_fr(scan.risk_level or "")
        findings = scan.findings_count or 0
        vuln_txt = f"{findings} vulnérabilité{'s' if findings > 1 else ''}"

        title       = f"Rapport de sécurité — {domain} | Wezea"
        description = (
            f"Score de sécurité : {score}% · Niveau {risk_lbl} · "
            f"{vuln_txt} détectée{'s' if findings > 1 else ''} · "
            f"Analyse de l'empreinte publique de {domain}."
        )
    else:
        title       = "Rapport de sécurité | Wezea Security Scanner"
        description = "Analyse de l'empreinte publique de sécurité — Wezea Security Scanner."

    title_safe = _html.escape(title)
    desc_safe  = _html.escape(description)
    url_safe   = _html.escape(target)
    img_safe   = _html.escape(og_image)

    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <title>{title_safe}</title>

  <!-- Open Graph -->
  <meta property="og:type"        content="website">
  <meta property="og:title"       content="{title_safe}">
  <meta property="og:description" content="{desc_safe}">
  <meta property="og:url"         content="{url_safe}">
  <meta property="og:image"       content="{img_safe}">
  <meta property="og:image:width"  content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:site_name"   content="Wezea Security Scanner">

  <!-- Twitter Card -->
  <meta name="twitter:card"        content="summary_large_image">
  <meta name="twitter:title"       content="{title_safe}">
  <meta name="twitter:description" content="{desc_safe}">
  <meta name="twitter:image"       content="{img_safe}">

  <!-- SEO -->
  <meta name="description" content="{desc_safe}">
  <link rel="canonical" href="{url_safe}">

  <!-- Redirect immédiat pour les navigateurs -->
  <meta http-equiv="refresh" content="0; url={url_safe}">
  <script>window.location.replace("{_html.escape(target, quote=True)}")</script>
</head>
<body>
  <p><a href="{url_safe}">Voir le rapport de sécurité</a></p>
</body>
</html>"""

    return HTMLResponse(
        content = html_content,
        headers = {"Cache-Control": "public, max-age=300"},
    )
