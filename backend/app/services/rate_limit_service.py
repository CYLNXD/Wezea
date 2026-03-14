"""
Rate Limit Service — Gestion des quotas de scan
=================================================
Fonctions extraites de main.py pour allèger le point d'entrée.
"""

import os
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from app.models import ScanHistory, ScanRateLimit, User


# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

ANON_SCAN_LIMIT  = int(os.getenv("ANON_SCAN_LIMIT", "1"))    # scans/jour par cookie (anonyme)
ANON_IP_DAY_CAP  = int(os.getenv("ANON_IP_DAY_CAP", "5"))    # scans/jour par IP (toutes sessions confondues)
FREE_SCAN_LIMIT  = int(os.getenv("FREE_SCAN_LIMIT", "5"))    # scans/jour free
COOKIE_SECURE    = os.getenv("COOKIE_SECURE", "true").lower() == "true"
COOKIE_SAMESITE  = os.getenv("COOKIE_SAMESITE", "none")      # "none" (prod HTTPS) ou "lax" (dev)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_real_ip(request: Request) -> str:
    """
    Extrait la vraie IP du client en tenant compte du reverse-proxy nginx.

    Priorité :
    1. X-Real-IP   — posé par nginx (`proxy_set_header X-Real-IP $remote_addr`)
    2. X-Forwarded-For — premier élément (client original, pas le proxy)
    3. request.client.host — fallback (= 127.0.0.1 derrière proxy sans config)

    Sans cette fonction, tous les utilisateurs anonymes partageraient le même
    bucket IP (127.0.0.1 = IP de nginx vu par uvicorn), ce qui provoquerait
    un 429 global dès 5 scans sur l'ensemble du serveur.
    """
    client_host = request.client.host if request.client else "127.0.0.1"

    # Ne faire confiance aux en-têtes proxy que si la connexion vient de localhost
    # (= nginx). Sinon, un client distant pourrait injecter X-Real-IP arbitraire.
    if client_host in ("127.0.0.1", "::1"):
        real_ip = request.headers.get("X-Real-IP", "").strip()
        if real_ip:
            return real_ip

        forwarded_for = request.headers.get("X-Forwarded-For", "").strip()
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

    return client_host


def _get_day_key() -> str:
    """Retourne la clé du jour courant, ex: '2026-03-04'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _get_day_start() -> datetime:
    """Retourne aujourd'hui 00:00:00 UTC."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


# ─────────────────────────────────────────────────────────────────────────────
# Rate limiting
# ─────────────────────────────────────────────────────────────────────────────

def _check_anon_rate_limit(client_id: str, ip: str, db) -> None:
    """
    Double verrou anonyme :
    1. Cookie wezea_cid  : 1 scan/jour par navigateur/appareil
    2. IP secondaire     : 5 scans/jour par IP (protection incognito / multi-sessions)
    """
    day = _get_day_key()

    # ── Verrou 1 : cookie par navigateur ─────────────────────────────────────
    record = db.query(ScanRateLimit).filter(
        ScanRateLimit.client_id == client_id,
        ScanRateLimit.date_key  == day,
    ).first()
    used = record.scan_count if record else 0
    if used >= ANON_SCAN_LIMIT:
        raise HTTPException(
            status_code=429,
            detail={
                "error":       "Limite journalière atteinte",
                "message":     (
                    f"Les visiteurs non connectés peuvent effectuer "
                    f"{ANON_SCAN_LIMIT} scan/jour. "
                    "Créez un compte gratuit pour 5 scans par jour."
                ),
                "limit":       ANON_SCAN_LIMIT,
                "used":        used,
                "remaining":   0,
                "day_key":     day,
                "upgrade_url": "/register",
                "type":        "anonymous",
            }
        )

    # ── Verrou 2 : IP secondaire (anti-incognito) ─────────────────────────────
    ip_key = f"ip:{ip}"
    ip_record = db.query(ScanRateLimit).filter(
        ScanRateLimit.client_id == ip_key,
        ScanRateLimit.date_key  == day,
    ).first()
    ip_used = ip_record.scan_count if ip_record else 0
    if ip_used >= ANON_IP_DAY_CAP:
        raise HTTPException(
            status_code=429,
            detail={
                "error":       "Limite journalière atteinte",
                "message":     (
                    "Nombre de scans anonymes maximum atteint depuis votre réseau. "
                    "Créez un compte gratuit pour 5 scans par jour."
                ),
                "limit":       ANON_IP_DAY_CAP,
                "used":        ip_used,
                "remaining":   0,
                "day_key":     day,
                "upgrade_url": "/register",
                "type":        "anonymous",
            }
        )


def _increment_anon_count(client_id: str, ip: str, db) -> None:
    """Incrémente le compteur cookie ET le compteur IP secondaire."""
    day = _get_day_key()

    # Compteur cookie
    record = db.query(ScanRateLimit).filter(
        ScanRateLimit.client_id == client_id,
        ScanRateLimit.date_key  == day,
    ).first()
    if record:
        record.scan_count += 1
    else:
        db.add(ScanRateLimit(client_id=client_id, date_key=day, scan_count=1))

    # Compteur IP secondaire
    ip_key = f"ip:{ip}"
    ip_record = db.query(ScanRateLimit).filter(
        ScanRateLimit.client_id == ip_key,
        ScanRateLimit.date_key  == day,
    ).first()
    if ip_record:
        ip_record.scan_count += 1
    else:
        db.add(ScanRateLimit(client_id=ip_key, date_key=day, scan_count=1))

    db.commit()


def _check_user_rate_limit(user: User, db) -> None:
    """Raise 429 si l'utilisateur connecté a dépassé sa limite journalière."""
    limit = user.scan_limit_per_day
    if limit is None:
        return  # illimité
    day_start = _get_day_start()
    count = db.query(ScanHistory).filter(
        ScanHistory.user_id    == user.id,
        ScanHistory.created_at >= day_start,
    ).count()
    if count >= limit:
        raise HTTPException(
            status_code=429,
            detail={
                "error":       "Limite journalière atteinte",
                "message":     f"Votre plan {user.plan} est limité à {limit} scans/jour.",
                "limit":       limit,
                "used":        count,
                "remaining":   0,
                "day_key":     _get_day_key(),
                "upgrade_url": "/upgrade",
                "type":        "free",
            }
        )
