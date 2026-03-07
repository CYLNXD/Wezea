"""
CyberHealth Scanner — Application Scanning Router
==================================================
Endpoints pour l'Application Scanning (applications web custom).
Réservé aux plans Starter et Pro.

POST   /apps                         → enregistrer une application
GET    /apps                         → lister les applications de l'utilisateur
DELETE /apps/{app_id}                → supprimer une application
GET    /apps/{app_id}/verify-info    → obtenir les instructions de vérification
POST   /apps/{app_id}/verify         → déclencher la vérification d'ownership
POST   /apps/{app_id}/scan           → lancer un scan applicatif (3/hour)
GET    /apps/{app_id}/results        → obtenir les derniers résultats
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import secrets
import urllib.parse
from datetime import datetime, timezone

import dns.resolver
import dns.exception

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.limiter import limiter
from app.models import VerifiedApp, User
from app.routers.auth_router import get_current_user
from app.scanner import ScoreEngine

router = APIRouter(prefix="/apps", tags=["Application Scanning"])

# ─────────────────────────────────────────────────────────────────────────────
# Validation URL (anti-SSRF)
# ─────────────────────────────────────────────────────────────────────────────

_DOMAIN_REGEX = re.compile(
    r"^(?!-)[A-Za-z0-9\-]{1,63}(?<!-)(\.[A-Za-z0-9\-]{1,63})*\.[A-Za-z]{2,}$"
)
_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "metadata.google.internal"}
_PRIVATE_CIDRS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("::1/128"),
]

# Limites par plan (None = illimité) — Application Scanning réservé au plan Dev
APP_LIMITS: dict[str, int | None] = {"dev": None}


def _parse_and_validate_url(raw: str) -> tuple[str, str]:
    """
    Valide une URL web et retourne (url_normalisée, host).
    Lève HTTPException 422 si invalide ou IP interne (anti-SSRF).
    """
    raw = raw.strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    try:
        parsed = urllib.parse.urlparse(raw)
    except Exception:
        raise HTTPException(status_code=422, detail="URL invalide.")

    host = parsed.hostname or ""
    if not host:
        raise HTTPException(status_code=422, detail="URL invalide — host manquant.")
    if host in _BLOCKED_HOSTS:
        raise HTTPException(status_code=422, detail="URL non autorisée (adresses locales).")
    try:
        addr = ipaddress.ip_address(host)
        if any(addr in cidr for cidr in _PRIVATE_CIDRS):
            raise HTTPException(status_code=422, detail="URL non autorisée (plages IP privées).")
    except ValueError:
        pass  # FQDN — la regex s'en charge
    if not _DOMAIN_REGEX.match(host):
        raise HTTPException(status_code=422, detail=f"'{host}' n'est pas un nom de domaine valide.")

    # Normaliser : schéma + host (on garde le path si présent)
    url_normalized = f"{parsed.scheme}://{host}"
    if parsed.port:
        url_normalized += f":{parsed.port}"
    if parsed.path and parsed.path != "/":
        url_normalized += parsed.path.rstrip("/")

    return url_normalized, host


def _require_plan(user: User) -> None:
    if user.is_admin:
        return
    if user.plan not in ("dev",):
        raise HTTPException(
            status_code=403,
            detail="L'Application Scanning est disponible avec le plan Dev (29,90 €/mois)."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Schémas Pydantic
# ─────────────────────────────────────────────────────────────────────────────

class AppCreate(BaseModel):
    name: str
    url: str
    verification_method: str = "dns"  # "dns" | "file"

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 100:
            raise ValueError("Le nom doit faire entre 1 et 100 caractères.")
        return v

    @field_validator("verification_method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        if v not in ("dns", "file"):
            raise ValueError("Méthode invalide. Utiliser 'dns' ou 'file'.")
        return v


class AppResponse(BaseModel):
    id: int
    name: str
    url: str
    domain: str
    verification_method: str
    verification_token: str
    is_verified: bool
    verified_at: datetime | None
    last_scan_at: datetime | None
    last_score: int | None
    last_risk_level: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AppScanResult(BaseModel):
    app_id: int
    name: str
    url: str
    score: int
    risk_level: str
    findings: list[dict]
    details: dict
    scanned_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Vérification d'ownership
# ─────────────────────────────────────────────────────────────────────────────

def _check_dns_verification(domain: str, token: str) -> bool:
    """Vérifie l'enregistrement TXT `_cyberhealth-verify.{domain}` = `cyberhealth-verify={token}`."""
    try:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = 8.0
        answers = resolver.resolve(f"_cyberhealth-verify.{domain}", "TXT")
        expected = f"cyberhealth-verify={token}"
        for rdata in answers:
            if expected in rdata.to_text().strip('"'):
                return True
    except Exception:
        pass
    return False


def _check_file_verification(domain: str, token: str) -> bool:
    """Vérifie `https://{domain}/.well-known/cyberhealth-verify.txt` contient le token."""
    import http.client, ssl
    path = "/.well-known/cyberhealth-verify.txt"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    for scheme_cls, port in [(http.client.HTTPSConnection, 443), (http.client.HTTPConnection, 80)]:
        try:
            conn = scheme_cls(domain, port, timeout=8)  # type: ignore[call-arg]
            conn.request("GET", path, headers={"User-Agent": "CyberHealth-Scanner/1.0"})
            r = conn.getresponse()
            if r.status == 200:
                body = r.read(256).decode("utf-8", errors="replace")
                if f"cyberhealth-verify={token}" in body:
                    return True
        except Exception:
            pass
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
def register_app(
    body: AppCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Enregistre une nouvelle application pour l'Application Scanning."""
    _require_plan(user)

    url, host = _parse_and_validate_url(body.url)

    # Vérifier doublon URL pour cet user
    existing = db.query(VerifiedApp).filter(
        VerifiedApp.user_id == user.id,
        VerifiedApp.url == url,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Cette URL est déjà enregistrée.")

    # Vérifier la limite du plan
    limit = APP_LIMITS.get(user.plan)
    if limit is not None and not user.is_admin:
        count = db.query(VerifiedApp).filter(VerifiedApp.user_id == user.id).count()
        if count >= limit:
            raise HTTPException(
                status_code=403,
                detail=f"Limite atteinte ({limit} application(s) max pour le plan {user.plan.capitalize()})."
            )

    token = secrets.token_urlsafe(24)
    app = VerifiedApp(
        user_id=user.id,
        name=body.name,
        url=url,
        domain=host,
        verification_method=body.verification_method,
        verification_token=token,
        is_verified=False,
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return AppResponse.model_validate(app)


@router.get("")
def list_apps(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Liste les applications enregistrées de l'utilisateur."""
    _require_plan(user)
    apps = db.query(VerifiedApp).filter(VerifiedApp.user_id == user.id).all()
    return [AppResponse.model_validate(a) for a in apps]


@router.delete("/{app_id}", status_code=204)
def delete_app(
    app_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Supprime une application enregistrée."""
    _require_plan(user)
    app = db.query(VerifiedApp).filter(
        VerifiedApp.id == app_id,
        VerifiedApp.user_id == user.id,
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application introuvable.")
    db.delete(app)
    db.commit()


@router.get("/{app_id}/verify-info")
def get_verify_info(
    app_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retourne les instructions de vérification d'ownership pour cette application."""
    _require_plan(user)
    app = db.query(VerifiedApp).filter(
        VerifiedApp.id == app_id,
        VerifiedApp.user_id == user.id,
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application introuvable.")

    instructions: dict = {
        "method": app.verification_method,
        "token": app.verification_token,
        "is_verified": app.is_verified,
    }

    if app.verification_method == "dns":
        instructions["record_type"]  = "TXT"
        instructions["record_name"]  = f"_cyberhealth-verify.{app.domain}"
        instructions["record_value"] = f"cyberhealth-verify={app.verification_token}"
        instructions["instructions"] = (
            f"Ajoutez l'enregistrement DNS suivant dans votre zone DNS :\n"
            f"  Type : TXT\n"
            f"  Nom  : _cyberhealth-verify.{app.domain}\n"
            f"  Valeur : cyberhealth-verify={app.verification_token}\n"
            "La propagation DNS peut prendre de quelques minutes à 48h."
        )
    else:  # file
        instructions["file_path"] = "/.well-known/cyberhealth-verify.txt"
        instructions["file_url"]  = f"{app.url}/.well-known/cyberhealth-verify.txt"
        instructions["file_content"] = f"cyberhealth-verify={app.verification_token}"
        instructions["instructions"] = (
            f"Créez le fichier suivant sur votre serveur web :\n"
            f"  Chemin : {app.url}/.well-known/cyberhealth-verify.txt\n"
            f"  Contenu : cyberhealth-verify={app.verification_token}\n"
            "Le fichier doit être accessible publiquement en HTTP/HTTPS."
        )

    return instructions


@router.post("/{app_id}/verify")
async def verify_ownership(
    app_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Tente de vérifier l'ownership de l'application (DNS ou fichier)."""
    _require_plan(user)
    app = db.query(VerifiedApp).filter(
        VerifiedApp.id == app_id,
        VerifiedApp.user_id == user.id,
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application introuvable.")

    loop = asyncio.get_event_loop()
    if app.verification_method == "dns":
        ok = await loop.run_in_executor(
            None, lambda: _check_dns_verification(app.domain, app.verification_token)
        )
    else:
        ok = await loop.run_in_executor(
            None, lambda: _check_file_verification(app.domain, app.verification_token)
        )

    if ok:
        app.is_verified = True
        app.verified_at = datetime.now(timezone.utc)
        db.commit()
        return {"verified": True, "message": "Propriété vérifiée avec succès ! Vous pouvez maintenant lancer un scan."}
    else:
        return {
            "verified": False,
            "message": (
                "Vérification échouée. Assurez-vous que l'enregistrement DNS / fichier est en place "
                "et réessayez. La propagation DNS peut prendre jusqu'à 48h."
            ),
        }


@router.post("/{app_id}/scan")
@limiter.limit("3/hour")
async def scan_app(
    request: Request,
    app_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Lance un scan applicatif sur une application vérifiée (max 3/hour)."""
    _require_plan(user)
    app = db.query(VerifiedApp).filter(
        VerifiedApp.id == app_id,
        VerifiedApp.user_id == user.id,
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application introuvable.")
    if not app.is_verified:
        raise HTTPException(
            status_code=403,
            detail="Vérifiez d'abord la propriété de l'application avant de lancer un scan."
        )

    from app.app_checks import AppAuditor

    try:
        auditor = AppAuditor(domain=app.domain)
        findings = await auditor.audit()
        details = auditor.get_details()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur pendant le scan : {exc}") from exc

    # Calcul du score
    engine = ScoreEngine(findings)
    score = engine.compute_score()
    risk_level = engine.risk_level(score)

    # Sauvegarder en DB
    findings_dicts = [f.to_dict() for f in findings]
    app.last_scan_at       = datetime.now(timezone.utc)
    app.last_score         = score
    app.last_risk_level    = risk_level
    app.last_findings_json = json.dumps(findings_dicts, ensure_ascii=False)
    app.last_details_json  = json.dumps(details, ensure_ascii=False)
    db.commit()

    return AppScanResult(
        app_id=app.id,
        name=app.name,
        url=app.url,
        score=score,
        risk_level=risk_level,
        findings=findings_dicts,
        details=details,
        scanned_at=app.last_scan_at,
    )


@router.get("/{app_id}/results")
def get_results(
    app_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retourne les derniers résultats de scan pour une application."""
    _require_plan(user)
    app = db.query(VerifiedApp).filter(
        VerifiedApp.id == app_id,
        VerifiedApp.user_id == user.id,
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application introuvable.")
    if not app.last_scan_at:
        raise HTTPException(status_code=404, detail="Aucun scan effectué pour cette application.")

    return AppScanResult(
        app_id=app.id,
        name=app.name,
        url=app.url,
        score=app.last_score or 0,
        risk_level=app.last_risk_level or "UNKNOWN",
        findings=app.get_last_findings(),
        details=app.get_last_details(),
        scanned_at=app.last_scan_at,
    )
