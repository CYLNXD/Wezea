"""
CyberHealth Scanner — API FastAPI
==================================
Endpoints :
    POST /scan              → Lance un audit complet (async)
    GET  /health            → Healthcheck
    POST /report/request    → Enregistre une demande de rapport PDF par email (lead gen)
    POST /generate-pdf      → Génère et retourne le rapport PDF en mémoire (BytesIO)

Middlewares :
    CORS, Rate-Limiting (SlowAPI), validation du domaine
"""


import io
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

# ── Logs JSON structurés — doit être appelé avant tout getLogger() ────────────
from app.logging_config import setup_logging
setup_logging()

logger = logging.getLogger("cyberhealth.main")

import json
import asyncio
from fastapi import FastAPI, HTTPException, Request, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
import ipaddress
from pydantic import BaseModel, field_validator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from sqlalchemy import func as sa_func
from app.limiter import limiter
from app.scanner import AuditManager
from app.services import report_service
from app.database import init_db, get_db, SessionLocal
from app.models import ScanHistory, ScanRateLimit, User
from app.routers.auth_router import router as auth_router, get_optional_user
from app.services import brevo_service
from app.routers.scans_router import router as scans_router
from app.routers.admin_router import router as admin_router
from app.routers.payment_router import router as payment_router
from app.routers.monitoring_router import router as monitoring_router
from app.routers.contact_router import router as contact_router
from app.routers.public_router import router as public_router
from app.routers.newsletter_router import router as newsletter_router
from app.routers.webhook_router import router as webhook_router
from app.routers.app_router import router as app_router
from app.metrics import record_request

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

API_VERSION   = "1.0.0"
RATE_LIMIT    = os.getenv("RATE_LIMIT", "10/minute")
# Trim whitespace autour de chaque origine (évite la config accidentelle "http://good.com, http://evil.com")
CORS_ORIGINS  = [o.strip() for o in os.getenv("CORS_ORIGINS", "https://wezea.net,https://www.wezea.net,https://scan.wezea.net").split(",") if o.strip()]
MAX_DOMAIN_LEN = 253  # RFC 1035

# Regex permissive pour valider un FQDN (pas les IPs internes)
DOMAIN_REGEX = re.compile(
    r"^(?!-)[A-Za-z0-9\-]{1,63}(?<!-)"
    r"(\.[A-Za-z0-9\-]{1,63})*\.[A-Za-z]{2,}$"
)

# Domaines et plages IP bloqués pour le scan (anti-SSRF)
BLOCKED_DOMAINS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "metadata.google.internal"}

_PRIVATE_CIDRS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("fc00::/7"),          # IPv6 ULA
    ipaddress.ip_network("::1/128"),
]


def _is_private_ip(value: str) -> bool:
    """Retourne True si la valeur est une adresse IP privée/réservée."""
    try:
        addr = ipaddress.ip_address(value)
        return any(addr in cidr for cidr in _PRIVATE_CIDRS)
    except ValueError:
        return False  # pas une IP — c'est un FQDN, la regex DOMAIN_REGEX s'en charge


def _resolve_and_check_ssrf(domain: str) -> None:
    """
    Résout le FQDN et vérifie que l'IP cible n'est pas une adresse privée/réservée.
    Protège contre le DNS rebinding : un attaquant pourrait posséder un domaine
    valide (p. ex. evil.attacker.com) qui résout vers 192.168.x.x ou 127.0.0.1.
    Lève HTTPException 422 si la cible est interne.
    """
    import socket as _socket
    try:
        resolved_ip = _socket.gethostbyname(domain)
    except _socket.gaierror:
        # Domaine non résolvable — le scanner remontera l'erreur lui-même
        return
    if _is_private_ip(resolved_ip):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "domain",
                "msg":   "Ce domaine résout vers une adresse IP interne. Scan non autorisé.",
            },
        )


# ─────────────────────────────────────────────────────────────────────────────
# Cycle de vie de l'application
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialisation / nettoyage au démarrage et à l'arrêt."""
    print(f"🚀 CyberHealth Scanner API v{API_VERSION} — démarrage")
    init_db()
    print("✅ Base de données initialisée")

    # Démarrer le scheduler (un seul worker via verrou fichier)
    from app.scheduler import start_scheduler, stop_scheduler
    scheduler_started = start_scheduler()
    if scheduler_started:
        print("✅ Scheduler monitoring démarré")

    yield

    if scheduler_started:
        stop_scheduler()
    print("🛑 CyberHealth Scanner API — arrêt propre")


# ─────────────────────────────────────────────────────────────────────────────
# Application FastAPI
# ─────────────────────────────────────────────────────────────────────────────

_DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# ─────────────────────────────────────────────────────────────────────────────
# Sentry — Error tracking (conditionnel : actif seulement si SENTRY_DSN est défini)
# ─────────────────────────────────────────────────────────────────────────────

_SENTRY_DSN = os.getenv("SENTRY_DSN", "")
if _SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn         = _SENTRY_DSN,
        environment = os.getenv("ENVIRONMENT", "production"),
        integrations = [
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
            LoggingIntegration(level=logging.WARNING, event_level=logging.ERROR),
        ],
        traces_sample_rate = float(os.getenv("SENTRY_TRACES_RATE", "0.05")),  # 5 % des requêtes
        send_default_pii   = False,   # RGPD : pas d'IP ni d'email dans les events
    )
    logger.info("Sentry initialisé (env=%s)", os.getenv("ENVIRONMENT", "production"))

app = FastAPI(
    title       = "CyberHealth Scanner API",
    description = (
        "Analyse l'empreinte de sécurité publique d'une entreprise "
        "à partir de son nom de domaine. Scan passif uniquement."
    ),
    version     = API_VERSION,
    lifespan    = lifespan,
    # Swagger/ReDoc désactivés en production (DEBUG=false)
    docs_url    = "/docs"  if _DEBUG else None,
    redoc_url   = "/redoc" if _DEBUG else None,
    openapi_url = "/openapi.json" if _DEBUG else None,
)

# Attacher le gestionnaire de rate limit
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — restreint aux origines autorisées
app.add_middleware(
    CORSMiddleware,
    allow_origins     = CORS_ORIGINS,
    allow_credentials = True,
    allow_methods     = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers     = ["Authorization", "Content-Type", "Accept", "Origin"],
)

# Routers
app.include_router(auth_router)
app.include_router(scans_router)
app.include_router(admin_router)
app.include_router(payment_router)
app.include_router(monitoring_router)
app.include_router(contact_router)
app.include_router(public_router)
app.include_router(newsletter_router)
app.include_router(webhook_router)
app.include_router(app_router)


# ─────────────────────────────────────────────────────────────────────────────
# Modèles Pydantic (requêtes & réponses)
# ─────────────────────────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    domain: str
    lang:   str = "fr"

    @field_validator("lang")
    @classmethod
    def validate_lang(cls, v: str) -> str:
        return v if v in ("fr", "en") else "fr"

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        v = v.strip().lower()
        # Supprimer le schéma si inclus par l'utilisateur
        for prefix in ("https://", "http://", "www."):
            if v.startswith(prefix):
                v = v[len(prefix):]
        # Supprimer le chemin éventuel
        v = v.split("/")[0].split("?")[0]

        if len(v) > MAX_DOMAIN_LEN:
            raise ValueError("Nom de domaine trop long (max 253 caractères).")
        if v in BLOCKED_DOMAINS:
            raise ValueError("Domaine non autorisé (adresses locales).")
        if _is_private_ip(v):
            raise ValueError("Domaine non autorisé (plages IP privées/réservées).")
        if not DOMAIN_REGEX.match(v):
            raise ValueError(
                f"'{v}' n'est pas un nom de domaine valide. "
                "Exemple : exemple.fr ou ma-startup.com"
            )
        return v


class ReportRequest(BaseModel):
    domain:     str
    email:      str
    company:    str | None = None
    first_name: str | None = None
    last_name:  str | None = None
    phone:      str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Adresse email invalide.")
        return v


class HealthResponse(BaseModel):
    status:     str
    version:    str
    timestamp:  str


class ScanResponse(BaseModel):
    scan_id:           str
    domain:            str
    scanned_at:        str
    security_score:    int
    risk_level:        str
    findings:          list[dict[str, Any]]
    dns_details:       dict[str, Any]
    ssl_details:       dict[str, Any]
    port_details:      dict[str, Any]
    recommendations:   list[str]
    scan_duration_ms:  int
    meta:              dict[str, Any]
    # Champs premium
    subdomain_details: dict[str, Any] = {}
    vuln_details:      dict[str, Any] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Middleware de logging des requêtes
# ─────────────────────────────────────────────────────────────────────────────

_SKIP_LOG_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico"})

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start    = time.perf_counter()
    response = await call_next(request)
    elapsed  = round((time.perf_counter() - start) * 1000, 2)

    path = request.url.path

    # Pas de log pour les endpoints de santé/doc (réduire le bruit)
    if path not in _SKIP_LOG_PATHS:
        ip = _get_real_ip(request)
        logger.info(
            "%s %s → %s",
            request.method, path, response.status_code,
            extra={
                "method":      request.method,
                "path":        path,
                "status":      response.status_code,
                "duration_ms": elapsed,
                "ip":          ip,
            },
        )

    # Enregistrement dans le buffer de métriques de performance
    record_request(
        path        = path,
        method      = request.method,
        status_code = response.status_code,
        duration_ms = elapsed,
    )
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Healthcheck",
    tags=["Système"],
)
async def health_check():
    """Vérifie que l'API est opérationnelle."""
    return HealthResponse(
        status    = "ok",
        version   = API_VERSION,
        timestamp = datetime.now(timezone.utc).isoformat(),
    )


GLOBAL_SCAN_TIMEOUT_SEC = int(os.getenv("GLOBAL_SCAN_TIMEOUT_SEC", "60"))  # timeout absolu d'un scan complet

ANON_SCAN_LIMIT  = int(os.getenv("ANON_SCAN_LIMIT", "1"))    # scans/jour par cookie (anonyme)
ANON_IP_DAY_CAP  = int(os.getenv("ANON_IP_DAY_CAP", "5"))    # scans/jour par IP (toutes sessions confondues)
FREE_SCAN_LIMIT  = int(os.getenv("FREE_SCAN_LIMIT", "5"))    # scans/jour free
COOKIE_SECURE    = os.getenv("COOKIE_SECURE", "true").lower() == "true"
COOKIE_SAMESITE  = os.getenv("COOKIE_SAMESITE", "none")      # "none" (prod HTTPS) ou "lax" (dev)


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
    real_ip = request.headers.get("X-Real-IP", "").strip()
    if real_ip:
        return real_ip

    forwarded_for = request.headers.get("X-Forwarded-For", "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return request.client.host if request.client else "127.0.0.1"


def _get_day_key() -> str:
    """Retourne la clé du jour courant, ex: '2026-03-04'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _get_day_start() -> datetime:
    """Retourne aujourd'hui 00:00:00 UTC."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


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


@app.get(
    "/client-id",
    summary = "Initialise l'identifiant client anonyme (cookie HttpOnly)",
    tags    = ["Scan"],
)
async def init_client_id(request: Request, response: Response):
    """
    Vérifie si un cookie `wezea_cid` existe. Si non, génère un UUID et le pose
    en cookie HttpOnly/Secure/SameSite pour identifier les visiteurs anonymes
    sans dépendre d'un header spoofable (X-Client-ID).
    Appelé une seule fois au chargement de l'app frontend.
    """
    existing = request.cookies.get("wezea_cid")
    if existing:
        return {"status": "existing"}

    new_id = str(uuid.uuid4())
    response.set_cookie(
        key      = "wezea_cid",
        value    = new_id,
        max_age  = 365 * 24 * 3600,   # 1 an
        httponly = True,
        secure   = COOKIE_SECURE,
        samesite = COOKIE_SAMESITE,
    )
    return {"status": "created"}


@app.get(
    "/scan/limits",
    summary = "Quota de scans de l'utilisateur courant",
    tags    = ["Scan"],
)
async def get_scan_limits(request: Request) -> dict:
    """
    Retourne le quota journalier (limit, used, remaining) pour l'appelant.
    - Anonyme  : basé sur le cookie wezea_cid (HttpOnly) ou fallback IP
    - Free     : basé sur l'historique du jour
    - Pro/Team : illimité
    """
    ip        = _get_real_ip(request)
    client_id = request.cookies.get("wezea_cid") or ip  # cookie HttpOnly > IP fallback

    db = SessionLocal()
    try:
        current_user: User | None = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            from app.auth import decode_token, hash_api_key as _hash_api_key
            payload = decode_token(token)
            if payload:
                current_user = db.query(User).filter(User.id == int(payload["sub"])).first()
            elif token.startswith("wsk_"):
                candidate = db.query(User).filter(User.api_key_hash == _hash_api_key(token)).first()
                if candidate and candidate.is_active and candidate.plan in ("dev",):
                    current_user = candidate

        if current_user:
            limit = current_user.scan_limit_per_day
            if limit is None:
                return {
                    "type":      "unlimited",
                    "limit":     None,
                    "used":      0,
                    "remaining": None,
                    "day_key":   _get_day_key(),
                }
            day_start = _get_day_start()
            used = db.query(ScanHistory).filter(
                ScanHistory.user_id    == current_user.id,
                ScanHistory.created_at >= day_start,
            ).count()
            return {
                "type":      "free",
                "limit":     limit,
                "used":      used,
                "remaining": max(0, limit - used),
                "day_key":   _get_day_key(),
            }
        else:
            day    = _get_day_key()
            record = db.query(ScanRateLimit).filter(
                ScanRateLimit.client_id == client_id,
                ScanRateLimit.date_key  == day,
            ).first()
            used = record.scan_count if record else 0
            return {
                "type":      "anonymous",
                "limit":     ANON_SCAN_LIMIT,
                "used":      used,
                "remaining": max(0, ANON_SCAN_LIMIT - used),
                "day_key":   day,
            }
    finally:
        db.close()


@app.post(
    "/scan",
    response_model  = ScanResponse,
    status_code     = status.HTTP_200_OK,
    summary         = "Lancer un audit de sécurité",
    description     = (
        "Analyse l'empreinte publique d'un domaine : DNS (SPF, DMARC), "
        "SSL/TLS, et exposition des ports critiques. "
        "Retourne un SecurityScore (0–100) avec détails et recommandations."
    ),
    tags=["Scan"],
)
async def run_scan(
    request: Request,
    body: ScanRequest,
) -> ScanResponse:
    """
    Lance un audit complet en parallèle sur le domaine fourni.
    Passif uniquement — aucun brute-force, aucune modification.
    """
    domain    = body.domain
    lang      = body.lang
    scan_id   = str(uuid.uuid4())
    ip        = _get_real_ip(request)
    client_id = request.cookies.get("wezea_cid") or ip  # cookie HttpOnly > IP fallback

    # ── Session DB ────────────────────────────────────────────────────────────
    db = SessionLocal()
    try:
        # ── Auth optionnelle : JWT ou clé API (wsk_) ─────────────────────────
        current_user: User | None = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            from app.auth import decode_token
            payload = decode_token(token)
            if payload:
                current_user = db.query(User).filter(User.id == int(payload["sub"])).first()
            elif token.startswith("wsk_"):
                # Clé API → plan Dev uniquement
                candidate = db.query(User).filter(User.api_key == token).first()
                if candidate and candidate.is_active and candidate.plan in ("dev",):
                    current_user = candidate

        # ── Rate limiting ─────────────────────────────────────────────────────
        if current_user:
            _check_user_rate_limit(current_user, db)
        else:
            _check_anon_rate_limit(client_id, ip, db)

        # ── Vérification SSRF (DNS rebinding) ─────────────────────────────────
        # La validation Pydantic bloque les IPs privées directes, mais un domaine
        # valide peut résoudre vers une IP interne → on vérifie après résolution DNS.
        _resolve_and_check_ssrf(domain)

        # ── Scan ──────────────────────────────────────────────────────────────
        try:
            scan_plan = current_user.plan if current_user else "anonymous"
            manager = AuditManager(domain, lang=lang, plan=scan_plan)
            # Timeout global : filet de sécurité absolu — évite qu'un scan bloque un worker
            result  = await asyncio.wait_for(manager.run(), timeout=GLOBAL_SCAN_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            detail_to: dict = {"error": "Le scan a dépassé le délai maximum autorisé.", "scan_id": scan_id}
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=detail_to)
        except Exception as exc:
            # Ne pas exposer str(exc) en production (fuite d'infos interne)
            detail: dict = {"error": "Erreur interne lors du scan.", "scan_id": scan_id}
            if _DEBUG:
                detail["message"] = str(exc)
            raise HTTPException(
                status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail      = detail,
            )

        result_dict = result.to_dict()

        # ── Incrémenter compteur anonyme ──────────────────────────────────────
        if not current_user:
            _increment_anon_count(client_id, ip, db)

        # ── Sauvegarder dans l'historique si connecté ─────────────────────────
        if current_user:
            # Persister les détails du scan pour la génération PDF depuis l'historique
            _scan_details = {
                "dns_details":       result_dict.get("dns_details", {}),
                "ssl_details":       result_dict.get("ssl_details", {}),
                "port_details":      result_dict.get("port_details", {}),
                "recommendations":   result_dict.get("recommendations", []),
                "subdomain_details": result_dict.get("subdomain_details", {}),
                "vuln_details":      result_dict.get("vuln_details", {}),
            }
            history = ScanHistory(
                user_id           = current_user.id,
                scan_uuid         = scan_id,
                domain            = result_dict["domain"],
                security_score    = result_dict["security_score"],
                risk_level        = result_dict["risk_level"],
                findings_count    = len(result_dict.get("findings", [])),
                findings_json     = json.dumps(result_dict.get("findings", [])),
                scan_details_json = json.dumps(_scan_details),
                scan_duration     = result_dict.get("scan_duration_ms"),
            )
            db.add(history)
            db.commit()

        # ── Capturer avant fermeture DB ───────────────────────────────────────
        user_plan = current_user.plan if current_user else "anonymous"
        is_auth   = current_user is not None
    finally:
        db.close()

    # ── Méta-données ──────────────────────────────────────────────────────────
    meta = {
        "scan_id":       scan_id,
        "freemium":      not is_auth or user_plan == "free",
        "full_report":   False,
        "authenticated": is_auth,
        "plan":          user_plan,
        "cta":           (
            "Get your complete expert report with a personalized action plan by calling /report/request"
            if lang == "en" else
            "Recevez votre rapport d'expert complet avec plan d'action "
            "personnalisé en appelant /report/request"
        ),
    }

    return ScanResponse(
        scan_id           = scan_id,
        domain            = result_dict["domain"],
        scanned_at        = result_dict["scanned_at"],
        security_score    = result_dict["security_score"],
        risk_level        = result_dict["risk_level"],
        findings          = result_dict["findings"],
        dns_details       = result_dict["dns_details"],
        ssl_details       = result_dict["ssl_details"],
        port_details      = result_dict["port_details"],
        recommendations   = result_dict["recommendations"],
        scan_duration_ms  = result_dict["scan_duration_ms"],
        meta              = meta,
        subdomain_details = result_dict.get("subdomain_details", {}),
        vuln_details      = result_dict.get("vuln_details", {}),
    )


@app.post(
    "/report/request",
    status_code = status.HTTP_202_ACCEPTED,
    summary     = "Demander le rapport PDF complet (Lead Gen)",
    description = (
        "Enregistre la demande de rapport d'expert complet par email. "
        "Déclenche l'envoi asynchrone du PDF."
    ),
    tags=["Lead Generation"],
)
@limiter.limit("5/minute")
async def request_full_report(request: Request, body: ReportRequest):
    """
    Point d'entrée Lead Gen :
    1. Valide l'email et le domaine.
    2. Ajoute le lead dans le CRM Brevo (liste dédiée + attribut DOMAIN).
    3. Lance en background : scan réel → génération PDF → envoi email.
    """
    lead_id = str(uuid.uuid4())

    # Lance la livraison du rapport en tâche de fond (non bloquant → 202 immédiat)
    asyncio.create_task(_deliver_lead_report(body.email, body.domain, lead_id))

    # Structure de prévisualisation retournée immédiatement
    report_sections = _build_report_structure(body.domain, body.email)

    return JSONResponse(
        status_code = status.HTTP_202_ACCEPTED,
        content     = {
            "lead_id":         lead_id,
            "status":          "queued",
            "message":         (
                f"Votre rapport d'expert sera envoyé à {body.email} "
                "dans les prochaines minutes."
            ),
            "report_preview":  report_sections,
            "next_steps": [
                "Vérifiez votre boîte mail (et les spams).",
                "Un consultant vous contactera sous 24h pour analyser vos résultats.",
                "Profitez de 30 min de consultation offerte incluse dans le rapport.",
            ],
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Background task : livraison du rapport PDF au lead
# ─────────────────────────────────────────────────────────────────────────────

_lead_logger = logging.getLogger("cyberhealth.lead")


async def _deliver_lead_report(email: str, domain: str, lead_id: str) -> None:
    """Enchaîne : CRM Brevo → scan → PDF → email (erreurs silencieuses)."""
    try:
        # 1. Enregistrer le lead dans le CRM Brevo
        await brevo_service.add_lead_contact(email, domain)

        # 2. Vérifier SSRF avant scan (silencieux — erreurs ignorées)
        try:
            _resolve_and_check_ssrf(domain)
        except HTTPException:
            return  # domaine interne → ne pas scanner, sortir silencieusement

        # Scanner le domaine (plan pro → tous les auditeurs actifs)
        manager = AuditManager(domain, plan="pro")
        result  = await manager.run()
        rd      = result.to_dict()

        # 3. Générer le PDF
        scan_data = {
            "domain":            domain,
            "scan_id":           lead_id,
            "security_score":    rd["security_score"],
            "risk_level":        rd["risk_level"],
            "findings":          rd["findings"],
            "dns_details":       rd.get("dns_details") or {},
            "ssl_details":       rd.get("ssl_details") or {},
            "port_details":      rd.get("port_details") or {},
            "subdomain_details": rd.get("subdomain_details") or {},
            "vuln_details":      rd.get("vuln_details") or {},
            "scanned_at":        rd["scanned_at"],
        }
        pdf_bytes = report_service.generate_pdf(scan_data, lang="fr")

        # 4. Envoyer le PDF par email
        await brevo_service.send_lead_report_email(
            email      = email,
            domain     = domain,
            pdf_bytes  = pdf_bytes,
            score      = rd["security_score"],
            risk_level = rd["risk_level"],
        )

        _lead_logger.info(
            "Lead report delivered: %s → %s (score=%s, risk=%s)",
            domain, email, rd["security_score"], rd["risk_level"],
        )

    except Exception as exc:
        _lead_logger.error(
            "Lead report delivery failed for %s / %s: %s",
            domain, email, exc,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Helper : structure du rapport PDF
# ─────────────────────────────────────────────────────────────────────────────

def _build_report_structure(domain: str, email: str) -> dict[str, Any]:
    """
    Définit les sections du rapport PDF expert.
    Le rapport réel sera généré par un worker async (Celery / ARQ).
    """
    return {
        "title":    f"Rapport CyberHealth Expert — {domain}",
        "sections": [
            {
                "id":    "executive_summary",
                "title": "1. Synthèse Dirigeant",
                "content": (
                    "Résumé du SecurityScore avec comparaison sectorielle, "
                    "top 3 des risques critiques à adresser en priorité, "
                    "et niveau de maturité cyber de l'entreprise."
                ),
            },
            {
                "id":    "technical_findings",
                "title": "3. Détail Technique des Vulnérabilités",
                "content": (
                    "Analyse complète de chaque finding avec preuve technique, "
                    "CVE associées, et niveau de criticité CVSS."
                ),
            },
            {
                "id":    "remediation_plan",
                "title": "4. Plan de Remédiation Prioritisé",
                "content": (
                    "Feuille de route en 3 phases (J+7 urgences critiques, "
                    "J+30 corrections importantes, J+90 optimisations), "
                    "avec estimation du temps et du coût par action."
                ),
            },
            {
                "id":    "compliance",
                "title": "5. Conformité Réglementaire",
                "content": (
                    "Analyse de la conformité RGPD, NIS2 et ISO 27001 "
                    "au regard des vulnérabilités identifiées. "
                    "Risques d'amendes et obligations légales."
                ),
            },
            {
                "id":    "consultation_offer",
                "title": "6. Offre de Consultation",
                "content": (
                    "30 minutes de consultation offerte avec un expert "
                    "CyberHealth pour analyser votre rapport et définir "
                    "votre roadmap de sécurité."
                ),
            },
        ],
        "recipient_email": email,
        "generated_for":   domain,
        "estimated_pages": 12,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Modèle pour la requête PDF
# ─────────────────────────────────────────────────────────────────────────────

class PDFRequest(BaseModel):
    """
    Corps de la requête POST /generate-pdf.
    Accepte le JSON complet issu de l'endpoint /scan.
    """
    scan_id:          str
    domain:           str
    scanned_at:       str
    security_score:   int
    risk_level:       str
    findings:         list[dict[str, Any]]
    dns_details:      dict[str, Any]          = {}
    ssl_details:      dict[str, Any]          = {}
    port_details:      dict[str, Any]         = {}
    recommendations:   list[str]              = []
    scan_duration_ms:  int                    = 0
    meta:              dict[str, Any]         = {}
    lang:              str                    = "fr"
    # Champs premium (optionnels — absents pour les scans free)
    subdomain_details: dict[str, Any]         = {}
    vuln_details:      dict[str, Any]         = {}


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint PDF
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/generate-pdf",
    status_code     = status.HTTP_200_OK,
    summary         = "Générer le rapport PDF expert",
    description     = (
        "Génère en mémoire (BytesIO) le rapport PDF complet à partir des données de scan. "
        "Retourne un fichier PDF directement téléchargeable. "
        "Nécessite le JSON complet issu de POST /scan."
    ),
    tags=["Rapport PDF"],
    responses={
        200: {
            "content":     {"application/pdf": {}},
            "description": "Rapport PDF généré avec succès.",
        }
    },
)
@limiter.limit("10/minute")
async def generate_pdf_report(
    request: Request,
    body: PDFRequest,
    current_user: User | None = Depends(get_optional_user),
) -> Response:
    """
    Génère le rapport PDF expert :
    1. Reçoit les données de scan complètes.
    2. Injecte dans le template Jinja2.
    3. Génère le PDF via WeasyPrint en mémoire.
    4. Retourne le flux binaire avec les bons headers HTTP.
    """
    audit_data = body.model_dump()
    lang       = body.lang if body.lang in ("fr", "en") else "fr"

    # ── Industry avg — injecté dans le contexte PDF pour le benchmark ─────────
    try:
        _db = SessionLocal()
        total  = _db.query(sa_func.count(ScanHistory.id)).scalar() or 0
        avg_v  = _db.query(sa_func.avg(ScanHistory.security_score)).scalar()
        if avg_v is not None and total >= 50:
            audit_data["industry_avg"] = round(float(avg_v))
        else:
            audit_data["industry_avg"] = 70   # baseline
        _db.close()
    except Exception:
        audit_data.setdefault("industry_avg", 70)

    # ── White-label : récupérer le branding Pro de l'utilisateur ─────────────
    white_label = None
    if current_user and current_user.plan in ("pro", "dev") and current_user.wb_enabled:
        white_label = {
            "enabled":       True,
            "company_name":  current_user.wb_company_name,
            "logo_b64":      current_user.wb_logo_b64,
            "primary_color": current_user.wb_primary_color,
        }

    # Nom de fichier : marque blanche si activée
    brand = (current_user.wb_company_name.lower().replace(" ", "-")
             if white_label and current_user.wb_company_name else "wezea")
    filename = f"{brand}-report-{body.domain}-{datetime.now().strftime('%Y%m%d')}.pdf"

    try:
        pdf_bytes = await _run_in_executor(
            report_service.generate_pdf, audit_data, lang, white_label
        )
    except RuntimeError as exc:
        # WeasyPrint non installé, libs système manquantes, ou erreur de rendu
        logger.error("PDF generation failed (RuntimeError): %s", exc)
        pdf_detail: dict = {"error": "Service de génération PDF indisponible."}
        if _DEBUG:
            pdf_detail["message"] = str(exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=pdf_detail)
    except Exception as exc:
        logger.error("PDF generation failed (Exception): %s", exc)
        pdf_detail2: dict = {"error": "Erreur lors de la génération du rapport."}
        if _DEBUG:
            pdf_detail2["message"] = str(exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=pdf_detail2)

    return Response(
        content      = pdf_bytes,
        media_type   = "application/pdf",
        headers      = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length":      str(len(pdf_bytes)),
            "X-Report-Domain":     body.domain,
            "X-Report-Score":      str(body.security_score),
        },
    )


async def _run_in_executor(fn, *args):
    """Exécute une fonction synchrone bloquante dans un thread séparé."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn, *args)


# ─────────────────────────────────────────────────────────────────────────────
# Gestionnaire d'erreurs global
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # En production : ne jamais exposer str(exc) ni le chemin complet (fuite d'infos)
    if _DEBUG:
        detail = {"error": "Erreur interne du serveur.", "detail": str(exc), "path": str(request.url.path)}
    else:
        detail = {"error": "Erreur interne du serveur. Veuillez réessayer plus tard."}
    return JSONResponse(
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
        content     = detail,
    )
