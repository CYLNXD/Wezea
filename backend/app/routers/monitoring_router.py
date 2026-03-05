"""
CyberHealth Scanner — Monitoring Router
=========================================
Endpoints pour la surveillance automatique hebdomadaire des domaines.
Réservé aux plans Starter et Pro.

GET  /monitoring/domains          → liste des domaines surveillés
POST /monitoring/domains          → ajouter un domaine
DELETE /monitoring/domains/{domain} → supprimer un domaine
GET  /monitoring/status           → état du scheduler + prochain scan
"""

import ipaddress
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.limiter import limiter
from app.models import MonitoredDomain, User
from app.routers.auth_router import get_current_user

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])

# ── Validation de domaine (anti-SSRF) ────────────────────────────────────────
# Dupliqué depuis main.py pour éviter l'import circulaire

_DOMAIN_REGEX = re.compile(
    r"^(?!-)[A-Za-z0-9\-]{1,63}(?<!-)"
    r"(\.[A-Za-z0-9\-]{1,63})*\.[A-Za-z]{2,}$"
)
_BLOCKED_DOMAINS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "metadata.google.internal"}
_PRIVATE_CIDRS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("::1/128"),
]


def _validate_monitored_domain(raw: str) -> str:
    """
    Nettoie et valide un FQDN pour le monitoring.
    Lève HTTPException 422 si invalide ou adresse interne (anti-SSRF).
    """
    v = raw.strip().lower()
    for prefix in ("https://", "http://", "www."):
        if v.startswith(prefix):
            v = v[len(prefix):]
    v = v.split("/")[0].split("?")[0]

    if len(v) > 253:
        raise HTTPException(status_code=422, detail="Nom de domaine trop long (max 253 caractères).")
    if v in _BLOCKED_DOMAINS:
        raise HTTPException(status_code=422, detail="Domaine non autorisé (adresses locales).")
    try:
        addr = ipaddress.ip_address(v)
        if any(addr in cidr for cidr in _PRIVATE_CIDRS):
            raise HTTPException(status_code=422, detail="Domaine non autorisé (plages IP privées/réservées).")
    except ValueError:
        pass  # c'est un FQDN, pas une IP — la regex s'en charge
    if not _DOMAIN_REGEX.match(v):
        raise HTTPException(
            status_code=422,
            detail=f"'{v}' n'est pas un nom de domaine valide. Exemple : exemple.fr"
        )
    return v

# Limites par plan (None = illimité)
DOMAIN_LIMITS: dict[str, int | None] = {"starter": 1, "pro": None}


class AddDomainRequest(BaseModel):
    domain: str
    alert_threshold: Optional[int] = 10  # Points de baisse pour déclencher une alerte
    checks_config: Optional[dict] = None  # {"dns":true,"ssl":true,"ports":true,...}


class UpdateDomainRequest(BaseModel):
    alert_threshold: Optional[int]  = None
    is_active:       Optional[bool] = None
    checks_config:   Optional[dict] = None
    scan_frequency:  Optional[str]  = None   # weekly | biweekly | monthly
    email_report:    Optional[bool] = None   # envoyer PDF par email à chaque scan


class DomainResponse(BaseModel):
    domain:               str
    last_score:           Optional[int]
    last_risk_level:      Optional[str]
    last_scan_at:         Optional[str]
    alert_threshold:      int
    is_active:            bool
    checks_config:        dict
    created_at:           str
    trend:                Optional[str]   # "up" | "down" | "stable" | None
    # Feature 2 — Surveillance élargie
    last_ssl_expiry_days: Optional[int]  = None
    last_open_ports:      Optional[list] = None
    last_technologies:    Optional[dict] = None
    # Feature 3 — Scan programmé
    scan_frequency:       str            = "weekly"
    email_report:         bool           = False


def _require_premium(user: User) -> None:
    if user.plan not in ("starter", "pro"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "Fonctionnalité réservée aux plans Starter et Pro.",
                "upgrade_url": "/upgrade",
            },
        )


@router.get("/domains", response_model=list[DomainResponse])
def list_monitored_domains(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Liste les domaines sous surveillance pour l'utilisateur connecté."""
    _require_premium(current_user)

    domains = (
        db.query(MonitoredDomain)
        .filter(
            MonitoredDomain.user_id == current_user.id,
            MonitoredDomain.is_active == True,
        )
        .order_by(MonitoredDomain.created_at.desc())
        .all()
    )

    import json as _json

    def _parse_json_list(raw: str | None) -> list | None:
        try:
            return _json.loads(raw) if raw else None
        except Exception:
            return None

    def _parse_json_dict(raw: str | None) -> dict | None:
        try:
            return _json.loads(raw) if raw else None
        except Exception:
            return None

    return [
        DomainResponse(
            domain                = d.domain,
            last_score            = d.last_score,
            last_risk_level       = d.last_risk_level,
            last_scan_at          = d.last_scan_at.isoformat() if d.last_scan_at else None,
            alert_threshold       = d.alert_threshold,
            is_active             = d.is_active,
            checks_config         = d.get_checks_config(),
            created_at            = d.created_at.isoformat(),
            trend                 = None,
            last_ssl_expiry_days  = d.last_ssl_expiry_days,
            last_open_ports       = _parse_json_list(d.last_open_ports),
            last_technologies     = _parse_json_dict(d.last_technologies),
            scan_frequency        = d.scan_frequency or "weekly",
            email_report          = bool(d.email_report),
        )
        for d in domains
    ]


@router.post("/domains", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/hour")
def add_monitored_domain(
    request: Request,
    body: AddDomainRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ajoute un domaine à la liste de surveillance."""
    _require_premium(current_user)

    # Valider le domaine (FQDN + anti-SSRF) — critique car le scheduler scannera ce host
    domain = _validate_monitored_domain(body.domain)

    # Vérifier la limite du plan (None = illimité)
    limit = DOMAIN_LIMITS.get(current_user.plan, 1)
    count = db.query(MonitoredDomain).filter(
        MonitoredDomain.user_id == current_user.id,
        MonitoredDomain.is_active == True,
    ).count()

    if limit is not None and count >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": f"Limite atteinte ({limit} domaine{'s' if limit > 1 else ''} max pour le plan {current_user.plan}).",
                "limit": limit,
                "used": count,
            },
        )

    # Vérifier si déjà présent (domain déjà nettoyé par _validate_monitored_domain)
    existing = db.query(MonitoredDomain).filter(
        MonitoredDomain.user_id == current_user.id,
        MonitoredDomain.domain  == domain,
    ).first()

    if existing:
        if existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": f"'{domain}' est déjà sous surveillance."},
            )
        # Réactiver si désactivé
        existing.is_active = True
        db.commit()
        return {"message": f"'{domain}' remis sous surveillance.", "domain": domain}

    import json as _json
    # Borner alert_threshold (cohérent avec le PATCH)
    threshold = max(1, min(50, body.alert_threshold)) if body.alert_threshold is not None else 10
    # Ajouter
    monitored = MonitoredDomain(
        user_id         = current_user.id,
        domain          = domain,
        alert_threshold = threshold,
        checks_config   = _json.dumps(body.checks_config) if body.checks_config else None,
    )
    db.add(monitored)
    db.commit()

    return {
        "message":    f"'{domain}' ajouté à la surveillance. Premier scan dans 24h.",
        "domain":     domain,
        "limit_used": count + 1,
        "limit_max":  limit,
    }


@router.delete("/domains/{domain}", status_code=status.HTTP_200_OK)
def remove_monitored_domain(
    domain: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retire un domaine de la surveillance."""
    _require_premium(current_user)

    domain = domain.lower().strip()
    monitored = db.query(MonitoredDomain).filter(
        MonitoredDomain.user_id == current_user.id,
        MonitoredDomain.domain  == domain,
    ).first()

    if not monitored:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": f"'{domain}' n'est pas sous surveillance."},
        )

    monitored.is_active = False
    db.commit()

    return {"message": f"'{domain}' retiré de la surveillance."}


@router.patch("/domains/{domain}")
def update_monitored_domain(
    domain: str,
    body: UpdateDomainRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Met à jour le seuil d'alerte ou le statut d'un domaine surveillé."""
    _require_premium(current_user)

    domain = domain.lower().strip()
    monitored = db.query(MonitoredDomain).filter(
        MonitoredDomain.user_id == current_user.id,
        MonitoredDomain.domain  == domain,
    ).first()

    if not monitored:
        raise HTTPException(
            status_code=404,
            detail={"error": f"'{domain}' n'est pas sous surveillance."},
        )

    import json as _json
    if body.alert_threshold is not None:
        monitored.alert_threshold = max(1, min(50, body.alert_threshold))
    if body.is_active is not None:
        monitored.is_active = body.is_active
    if body.checks_config is not None:
        monitored.checks_config = _json.dumps(body.checks_config)
    if body.scan_frequency is not None:
        if body.scan_frequency in ("weekly", "biweekly", "monthly"):
            monitored.scan_frequency = body.scan_frequency
    if body.email_report is not None:
        monitored.email_report = body.email_report

    db.commit()
    return {"message": f"'{domain}' mis à jour.", "domain": domain}


@router.get("/status")
def monitoring_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retourne l'état du monitoring pour l'utilisateur."""
    _require_premium(current_user)

    limit = DOMAIN_LIMITS.get(current_user.plan, 1)
    count = db.query(MonitoredDomain).filter(
        MonitoredDomain.user_id == current_user.id,
        MonitoredDomain.is_active == True,
    ).count()

    return {
        "plan":           current_user.plan,
        "domains_used":   count,
        "domains_max":    limit,   # None = illimité
        "scan_frequency": "weekly",
        "next_scan":      "Lundi prochain à 06:00 UTC",
    }
