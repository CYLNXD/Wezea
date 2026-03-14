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
from app.routers.scan_router import router as scan_router
from app.routers.admin_router import router as admin_router
from app.routers.payment_router import router as payment_router
from app.routers.monitoring_router import router as monitoring_router
from app.routers.contact_router import router as contact_router
from app.routers.public_router import router as public_router
from app.routers.newsletter_router import router as newsletter_router
from app.routers.webhook_router import router as webhook_router
from app.routers.app_router import router as app_router
from app.routers.partner_router import router as partner_router
from app.routers.remediation_router import router as remediation_router
from app.routers.compliance_router import router as compliance_router
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

# Attacher le gestionnaire de rate limit (avec headers CORS pour éviter
# que le navigateur bloque les réponses 429 cross-origin)
app.state.limiter = limiter

def _rate_limit_handler_with_cors(request, exc):
    from starlette.responses import JSONResponse
    origin = request.headers.get("origin", "")
    headers = {}
    if origin in CORS_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        status_code=429,
        content={"error": "Rate limit exceeded", "detail": str(exc.detail)},
        headers=headers,
    )

app.add_exception_handler(RateLimitExceeded, _rate_limit_handler_with_cors)

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
app.include_router(partner_router)
app.include_router(remediation_router)
app.include_router(compliance_router)
app.include_router(scan_router)


# ─────────────────────────────────────────────────────────────────────────────
# Modèles Pydantic — re-exports pour compatibilité tests
# ─────────────────────────────────────────────────────────────────────────────

from app.routers.scan_router import (  # noqa: E402, F401
    ScanRequest, ReportRequest, ScanResponse, PDFRequest,
    _build_report_structure, _deliver_lead_report, _run_in_executor,
)


class HealthResponse(BaseModel):
    status:     str
    version:    str
    timestamp:  str


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

# ── Rate limiting — importé de rate_limit_service (re-exports pour compatibilité tests) ──
from app.services.rate_limit_service import (  # noqa: E402
    ANON_SCAN_LIMIT, ANON_IP_DAY_CAP, FREE_SCAN_LIMIT,
    COOKIE_SECURE, COOKIE_SAMESITE,
    _get_real_ip, _get_day_key, _get_day_start,
    _check_anon_rate_limit, _increment_anon_count, _check_user_rate_limit,
)




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
