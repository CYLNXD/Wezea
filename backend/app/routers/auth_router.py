"""
Auth Router — Register, Login, Me, Profile (RGPD), Delete Account, Regenerate API Key, White-label
"""

import re
import secrets

from datetime import datetime, timedelta, timezone
from typing import Optional

import base64
import re as _re
from fastapi import APIRouter, Depends, HTTPException, Request, status, Header, BackgroundTasks, UploadFile, File
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

from app.auth import (
    hash_password, verify_password, needs_rehash,
    create_access_token, decode_token,
    generate_api_key,
)
import os
from app.database import get_db
from app.limiter import limiter
from app.models import User, LoginAttempt
from app.services.brevo_service import (
    send_welcome_email,
    add_registered_user_contact,
    update_brevo_contact,
    delete_brevo_contact,
    send_password_reset_email,
)
import asyncio

# ─── Login lockout (DB-backed — partagé entre tous les workers uvicorn) ───────
# Avantage vs dict in-memory : fonctionne avec plusieurs workers simultanés.
_LOCKOUT_WINDOW_MIN = 15   # fenêtre glissante en minutes
_LOCKOUT_MAX        = 5    # échecs dans cette fenêtre avant verrouillage


def _check_lockout(ip: str, db: Session) -> None:
    """Lève HTTP 429 si l'IP dépasse _LOCKOUT_MAX échecs dans les 15 dernières minutes."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=_LOCKOUT_WINDOW_MIN)
    recent = (
        db.query(LoginAttempt)
        .filter(LoginAttempt.ip == ip, LoginAttempt.failed_at >= cutoff)
        .count()
    )
    if recent >= _LOCKOUT_MAX:
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives échouées. Réessayez dans 15 minutes.",
        )


def _record_failure(ip: str, db: Session) -> None:
    """Enregistre un échec et purge les entrées âgées de plus d'1 heure."""
    db.add(LoginAttempt(ip=ip))
    cutoff_cleanup = datetime.now(timezone.utc) - timedelta(hours=1)
    db.query(LoginAttempt).filter(LoginAttempt.failed_at < cutoff_cleanup).delete()
    db.commit()


def _clear_failures(ip: str, db: Session) -> None:
    """Supprime tous les échecs pour cette IP après un login réussi."""
    db.query(LoginAttempt).filter(LoginAttempt.ip == ip).delete()
    db.commit()

router = APIRouter(prefix="/auth", tags=["auth"])

PASSWORD_MIN = 8
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
_DEBUG = os.getenv("DEBUG", "false").lower() == "true"


# ─── Schemas ──────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < PASSWORD_MIN:
            raise ValueError(f"Password must be at least {PASSWORD_MIN} characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    id: int
    email: str
    plan: str
    api_key: Optional[str]
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    google_id: Optional[str] = None
    created_at: str
    is_admin: bool = False
    mfa_enabled: bool = False


class GoogleAuthRequest(BaseModel):
    id_token: str


class UpdateProfileRequest(BaseModel):
    first_name: Optional[str] = None
    last_name:  Optional[str] = None

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def strip_and_limit(cls, v):
        if v is not None:
            v = str(v).strip()[:100]
        return v or None


class DeleteAccountRequest(BaseModel):
    password: str  # confirmation obligatoire


# ─── Dependency : get current user from Bearer token OR API key ───────────────
def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1]

    # Essayer JWT d'abord
    payload = decode_token(token)
    if payload:
        user = db.query(User).filter(User.id == int(payload["sub"])).first()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found")
        return user

    # Fallback : API key (format wsk_<base64url>, plan Dev uniquement)
    # Note : token_urlsafe(32) génère ~43 chars base64url — pas 64 hex, pas isalnum()
    if token.startswith("wsk_"):
        user = db.query(User).filter(User.api_key == token).first()
        if user and user.is_active and user.plan in ("dev",):
            return user

    raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_optional_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Returns user or None — for endpoints that work both logged in and anonymous."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1]

    # JWT d'abord
    payload = decode_token(token)
    if payload:
        return db.query(User).filter(User.id == int(payload["sub"])).first()

    # Fallback API key (wsk_ prefix, plan Dev)
    if token.startswith("wsk_"):
        user = db.query(User).filter(User.api_key == token).first()
        if user and user.is_active and user.plan in ("dev",):
            return user

    return None


# ─── Endpoints ────────────────────────────────────────────────────────────────
def _send_welcome_sync(email: str) -> None:
    """
    Wrapper synchrone pour les tâches de fond à l'inscription :
    1. Envoie l'email de bienvenue
    2. Crée le contact dans Brevo (s'il n'existe pas déjà)
    Les deux sont non-bloquants et silencieux en cas d'erreur.
    """
    import asyncio
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(send_welcome_email(email))
        loop.run_until_complete(add_registered_user_contact(email))
        loop.close()
    except Exception:
        pass


@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit("10/hour")
def register(
    request: Request,
    req: RegisterRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=req.email,
        password_hash=hash_password(req.password),
        plan="free",
        api_key=generate_api_key(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.email, user.plan)

    # Email de bienvenue en tâche de fond (non-bloquant)
    background_tasks.add_task(_send_welcome_sync, user.email)

    return TokenResponse(
        access_token=token,
        user={"id": user.id, "email": user.email, "plan": user.plan, "api_key": user.api_key,
              "first_name": user.first_name, "last_name": user.last_name, "google_id": user.google_id,
              "is_admin": bool(user.is_admin)},
    )


@router.post("/login")
@limiter.limit("30/minute")
def login(request: Request, req: LoginRequest, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    _check_lockout(ip, db)

    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        _record_failure(ip, db)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    _clear_failures(ip, db)

    # ── Rehash transparent bcrypt → argon2 (migration silencieuse) ────────────
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(req.password)
        db.commit()

    # ── 2FA : si activé, retourner un token intermédiaire (step=mfa) ──────────
    if user.mfa_enabled and user.mfa_secret:
        mfa_token = create_access_token(user.id, user.email, user.plan, step="mfa")
        return {"mfa_required": True, "mfa_token": mfa_token}

    token = create_access_token(user.id, user.email, user.plan)
    return TokenResponse(
        access_token=token,
        user={"id": user.id, "email": user.email, "plan": user.plan, "api_key": user.api_key,
              "first_name": user.first_name, "last_name": user.last_name, "google_id": user.google_id,
              "is_admin": bool(user.is_admin), "mfa_enabled": bool(user.mfa_enabled)},
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        plan=current_user.plan,
        api_key=current_user.api_key,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        google_id=current_user.google_id,
        created_at=current_user.created_at.isoformat(),
        is_admin=bool(current_user.is_admin),
        mfa_enabled=bool(current_user.mfa_enabled),
    )


# ─── Profil RGPD ───────────────────────────────────────────────────────────────

@router.patch("/profile", response_model=UserResponse)
def update_profile(
    req: UpdateProfileRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Met à jour le prénom et/ou le nom de l'utilisateur connecté."""
    if req.first_name is not None:
        current_user.first_name = req.first_name
    if req.last_name is not None:
        current_user.last_name = req.last_name
    db.commit()
    db.refresh(current_user)

    # Sync Brevo en arrière-plan (ne bloque pas la réponse)
    # update_brevo_contact(email, plan) — on transmet le plan, pas le nom (mauvaise signature corrigée)
    def _sync_brevo():
        asyncio.run(update_brevo_contact(current_user.email, current_user.plan))
    background_tasks.add_task(_sync_brevo)

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        plan=current_user.plan,
        api_key=current_user.api_key,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        google_id=current_user.google_id,
        created_at=current_user.created_at.isoformat(),
        is_admin=bool(current_user.is_admin),
        mfa_enabled=bool(current_user.mfa_enabled),
    )


@router.delete("/account", status_code=200)
def delete_account(
    req: DeleteAccountRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Suppression définitive du compte (RGPD — droit à l'effacement).
    Exige la confirmation du mot de passe (non applicable aux comptes Google).
    Supprime l'utilisateur ET tous ses scans (cascade via SQLAlchemy).
    """
    is_google = bool(current_user.google_id) and current_user.password_hash.startswith("!google:")
    if not is_google:
        # Comptes classiques : vérifier le mot de passe
        if not verify_password(req.password, current_user.password_hash):
            raise HTTPException(status_code=400, detail="Mot de passe incorrect")
    # Comptes Google : pas de mot de passe — l'authentification JWT suffit

    email_to_delete = current_user.email  # capturer avant suppression
    db.delete(current_user)
    db.commit()

    # Suppression Brevo en arrière-plan
    def _delete_brevo():
        asyncio.run(delete_brevo_contact(email_to_delete))
    background_tasks.add_task(_delete_brevo)

    return {"message": "Compte supprimé définitivement"}


@router.post("/api-key/regenerate")
def regenerate_api_key(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.api_key = generate_api_key()
    db.commit()
    return {"api_key": current_user.api_key}


# ─── Change password ───────────────────────────────────────────────────────────

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < PASSWORD_MIN:
            raise ValueError(f"Password must be at least {PASSWORD_MIN} characters")
        return v


@router.post("/change-password", status_code=200)
@limiter.limit("10/hour")
def change_password(
    request: Request,
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the password of the currently authenticated user."""
    # Utilisateurs Google — pas de mot de passe
    if current_user.google_id and current_user.password_hash.startswith("!google:"):
        raise HTTPException(status_code=400, detail="Votre compte est lié à Google. Connectez-vous via Google.")
    if not verify_password(req.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect")

    current_user.password_hash = hash_password(req.new_password)
    db.commit()
    return {"message": "Mot de passe mis à jour avec succès"}


# ─── Change email ───────────────────────────────────────────────────────────────

class ChangeEmailRequest(BaseModel):
    new_email: EmailStr
    current_password: str


@router.post("/change-email", status_code=200)
@limiter.limit("5/hour")
def change_email(
    request: Request,
    req: ChangeEmailRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the email of the currently authenticated user."""
    # Utilisateurs Google — email géré par Google
    if current_user.google_id and current_user.password_hash.startswith("!google:"):
        raise HTTPException(status_code=400, detail="Votre compte est lié à Google. L'email est géré par Google.")
    if not verify_password(req.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect")
    # Vérifier que le nouvel email n'est pas déjà utilisé
    existing = db.query(User).filter(User.email == req.new_email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Cet email est déjà utilisé par un autre compte.")
    current_user.email = req.new_email
    db.commit()
    return {"message": "Email mis à jour avec succès"}


# ─── Google OAuth ───────────────────────────────────────────────────────────────

@router.post("/google", response_model=TokenResponse, status_code=200)
@limiter.limit("20/hour")
def google_auth(
    request: Request,
    req: GoogleAuthRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Authentification via Google Identity Services.
    Vérifie le id_token Google, crée ou retrouve l'utilisateur, retourne un JWT.
    """
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google OAuth non configuré")

    # ── Vérification du token Google ─────────────────────────────────────────
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
        idinfo = google_id_token.verify_oauth2_token(
            req.id_token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except ValueError as exc:
        detail = f"Token Google invalide : {exc}" if _DEBUG else "Token Google invalide."
        raise HTTPException(status_code=401, detail=detail)

    email      = (idinfo.get("email") or "").lower().strip()
    google_sub = idinfo.get("sub")
    first_name = idinfo.get("given_name")
    last_name  = idinfo.get("family_name")

    if not email or not idinfo.get("email_verified"):
        raise HTTPException(status_code=400, detail="Email Google non vérifié")

    # ── Trouver ou créer l'utilisateur ────────────────────────────────────────
    # Recherche par google_id en priorité, puis fallback par email (insensible à la casse)
    user = (
        db.query(User).filter(User.google_id == google_sub).first()
        or db.query(User).filter(User.email == email).first()
    )
    is_new = False

    if not user:
        is_new = True
        user = User(
            email=email,
            password_hash=f"!google:{google_sub}",   # hash inutilisable volontairement
            plan="free",
            api_key=generate_api_key(),
            google_id=google_sub,
            first_name=first_name,
            last_name=last_name,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        background_tasks.add_task(_send_welcome_sync, user.email)
    else:
        # Compte existant — lier Google si pas encore fait
        changed = False
        if not user.google_id and google_sub:
            user.google_id = google_sub
            changed = True
        if first_name and not user.first_name:
            user.first_name = first_name
            changed = True
        if last_name and not user.last_name:
            user.last_name = last_name
            changed = True
        if changed:
            db.commit()
            db.refresh(user)

    token = create_access_token(user.id, user.email, user.plan)
    return TokenResponse(
        access_token=token,
        user={
            "id": user.id, "email": user.email, "plan": user.plan,
            "api_key": user.api_key, "first_name": user.first_name,
            "last_name": user.last_name, "google_id": user.google_id,
            "is_admin": bool(user.is_admin),
        },
    )


# ─── Mot de passe oublié / Réinitialisation ───────────────────────────────────

_FRONTEND_URL = os.getenv("FRONTEND_URL", "https://wezea.net")
_RESET_TOKEN_EXPIRY_HOURS = 1


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < PASSWORD_MIN:
            raise ValueError(f"Password must be at least {PASSWORD_MIN} characters")
        return v


@router.post("/forgot-password", status_code=200)
@limiter.limit("5/hour")
def forgot_password(
    request: Request,
    req: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Envoie un email de réinitialisation de mot de passe.
    Retourne toujours 200 pour éviter l'énumération d'emails (user valide/invalide indiscernables).
    Ne fonctionne pas pour les comptes Google (pas de mot de passe local).
    """
    _MSG = "Si cet email est enregistré, vous recevrez un lien de réinitialisation dans quelques minutes."

    user = db.query(User).filter(User.email == req.email).first()
    if user and not (user.google_id and user.password_hash.startswith("!google:")):
        token = secrets.token_urlsafe(32)
        user.password_reset_token   = token
        user.password_reset_expires = datetime.now(timezone.utc) + timedelta(hours=_RESET_TOKEN_EXPIRY_HOURS)
        db.commit()

        reset_url = f"{_FRONTEND_URL}/?reset_token={token}"

        def _send_reset_email():
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(send_password_reset_email(req.email, reset_url))
            except Exception:
                pass
            finally:
                loop.close()

        background_tasks.add_task(_send_reset_email)

    return {"message": _MSG}


@router.post("/reset-password", status_code=200)
@limiter.limit("10/hour")
def reset_password(
    request: Request,
    req: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Réinitialise le mot de passe via le token reçu par email.
    Le token est à usage unique et expire après 1 heure.
    """
    if not req.token or len(req.token) < 10:
        raise HTTPException(status_code=400, detail="Token invalide.")

    user = (
        db.query(User)
        .filter(User.password_reset_token == req.token)
        .first()
    )

    if not user or not user.password_reset_expires:
        raise HTTPException(status_code=400, detail="Lien invalide ou déjà utilisé.")

    # SQLite retourne des datetimes naïfs — normalisation timezone-safe
    expires = user.password_reset_expires
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > expires:
        user.password_reset_token   = None
        user.password_reset_expires = None
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="Ce lien a expiré. Faites une nouvelle demande de réinitialisation.",
        )

    user.password_hash          = hash_password(req.new_password)
    user.password_reset_token   = None
    user.password_reset_expires = None
    db.commit()

    return {"message": "Mot de passe mis à jour avec succès."}


# ── White-label endpoints (Pro) ───────────────────────────────────────────────

_HEX_COLOR_RE = _re.compile(r'^#[0-9A-Fa-f]{6}$')
_LOGO_MAX_BYTES = 200 * 1024   # 200 Ko
_ALLOWED_MIME   = {"image/png", "image/jpeg", "image/svg+xml", "image/webp"}


class WhiteLabelUpdate(BaseModel):
    enabled:       Optional[bool] = None
    company_name:  Optional[str]  = None
    primary_color: Optional[str]  = None   # "#RRGGBB"


@router.get("/white-label")
def get_white_label(
    current_user: User = Depends(get_current_user),
):
    """Retourne les settings de marque blanche (sans le blob base64 complet)."""
    if current_user.plan not in ("pro", "dev"):
        raise HTTPException(status_code=403, detail="White-label réservé aux plans Pro et Dev.")
    return {
        "enabled":       bool(current_user.wb_enabled),
        "company_name":  current_user.wb_company_name,
        "primary_color": current_user.wb_primary_color,
        "has_logo":      bool(current_user.wb_logo_b64),
        # On renvoie le logo uniquement pour prévisualisation (tronqué si trop long)
        "logo_b64":      current_user.wb_logo_b64,
    }


@router.patch("/white-label")
def update_white_label(
    req: WhiteLabelUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Met à jour les paramètres de marque blanche."""
    if current_user.plan not in ("pro", "dev"):
        raise HTTPException(status_code=403, detail="White-label réservé aux plans Pro et Dev.")

    if req.enabled is not None:
        current_user.wb_enabled = req.enabled

    if req.company_name is not None:
        name = req.company_name.strip()
        if len(name) > 100:
            raise HTTPException(status_code=422, detail="Nom trop long (max 100 caractères).")
        current_user.wb_company_name = name or None

    if req.primary_color is not None:
        color = req.primary_color.strip()
        if color and not _HEX_COLOR_RE.match(color):
            raise HTTPException(status_code=422, detail="Couleur invalide — format attendu : #RRGGBB")
        current_user.wb_primary_color = color or None

    db.commit()
    db.refresh(current_user)
    return {
        "enabled":       bool(current_user.wb_enabled),
        "company_name":  current_user.wb_company_name,
        "primary_color": current_user.wb_primary_color,
        "has_logo":      bool(current_user.wb_logo_b64),
    }


@router.post("/white-label/logo")
async def upload_white_label_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload et stocke le logo en base64 (PNG / JPG / SVG / WebP, max 200 Ko)."""
    if current_user.plan not in ("pro", "dev"):
        raise HTTPException(status_code=403, detail="White-label réservé aux plans Pro et Dev.")

    content_type = (file.content_type or "").lower()

    # Fallback : détecter le type via l'extension si le browser ne l'envoie pas
    if not content_type or content_type not in _ALLOWED_MIME:
        _ext_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "svg": "image/svg+xml", "webp": "image/webp"}
        ext = (file.filename or "").rsplit(".", 1)[-1].lower()
        content_type = _ext_map.get(ext, content_type)

    if content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=422,
            detail=f"Format non supporté ({content_type}). Utilisez PNG, JPG, SVG ou WebP.",
        )

    data = await file.read()
    if len(data) > _LOGO_MAX_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"Logo trop volumineux ({len(data)//1024} Ko). Maximum : 200 Ko.",
        )

    # Stocker en data URI pour utilisation directe dans le template
    b64 = base64.b64encode(data).decode("utf-8")
    data_uri = f"data:{content_type};base64,{b64}"

    current_user.wb_logo_b64 = data_uri
    db.commit()
    return {"status": "ok", "has_logo": True, "size_kb": len(data) // 1024}


@router.delete("/white-label/logo")
def delete_white_label_logo(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Supprime le logo de marque blanche."""
    if current_user.plan not in ("pro", "dev"):
        raise HTTPException(status_code=403, detail="White-label réservé aux plans Pro et Dev.")
    current_user.wb_logo_b64 = None
    db.commit()
    return {"status": "ok", "has_logo": False}


# ─────────────────────────────────────────────────────────────────────────────
# Intégrations Slack / Teams
# ─────────────────────────────────────────────────────────────────────────────

_WEBHOOK_URL_RE = re.compile(
    r"^https://(hooks\.slack\.com/|[a-z0-9-]+\.webhook\.office\.com/).{10,}",
    re.IGNORECASE,
)


class IntegrationsRequest(BaseModel):
    slack_webhook_url: Optional[str] = None   # "" pour effacer
    teams_webhook_url: Optional[str] = None   # "" pour effacer


@router.get("/integrations")
def get_integrations(
    current_user: User = Depends(get_current_user),
):
    """Retourne les URLs de webhook configurées (masquées)."""
    def _mask(url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        return url[:30] + "…" if len(url) > 30 else url

    return {
        "slack_webhook_url": _mask(current_user.slack_webhook_url),
        "teams_webhook_url": _mask(current_user.teams_webhook_url),
        "slack_configured": bool(current_user.slack_webhook_url),
        "teams_configured": bool(current_user.teams_webhook_url),
    }


@router.patch("/integrations")
def update_integrations(
    body: IntegrationsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Met à jour les URLs de webhook Slack / Teams.
    Passer une chaîne vide pour supprimer l'intégration.
    Réservé aux plans Pro et Dev.
    """
    if current_user.plan not in ("pro", "dev"):
        raise HTTPException(
            status_code=403,
            detail="Les intégrations Slack/Teams sont réservées aux plans Pro et Dev.",
        )

    if body.slack_webhook_url is not None:
        url = body.slack_webhook_url.strip()
        if url == "":
            current_user.slack_webhook_url = None
        elif not _WEBHOOK_URL_RE.match(url):
            raise HTTPException(
                status_code=422,
                detail="L'URL Slack doit commencer par https://hooks.slack.com/",
            )
        else:
            current_user.slack_webhook_url = url

    if body.teams_webhook_url is not None:
        url = body.teams_webhook_url.strip()
        if url == "":
            current_user.teams_webhook_url = None
        elif not url.startswith("https://"):
            raise HTTPException(
                status_code=422,
                detail="L'URL Teams doit commencer par https://",
            )
        else:
            current_user.teams_webhook_url = url

    db.commit()
    return {
        "status": "ok",
        "slack_configured": bool(current_user.slack_webhook_url),
        "teams_configured": bool(current_user.teams_webhook_url),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2FA — TOTP (Google Authenticator / Authy / Bitwarden…)
# ─────────────────────────────────────────────────────────────────────────────

class TotpVerifyRequest(BaseModel):
    code: str          # 6 chiffres
    mfa_token: Optional[str] = None   # token intermédiaire (step=mfa) pour confirm-login


class TotpDisableRequest(BaseModel):
    code: str          # vérification avant désactivation
    password: str      # double confirmation


@router.post("/2fa/setup")
def setup_2fa(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Génère un secret TOTP et retourne :
    - l'URI otpauth:// pour scanner le QR code
    - le secret brut (pour saisie manuelle)
    - un QR code PNG en base64
    La 2FA n'est PAS encore activée — il faut appeler /2fa/verify pour confirmer.
    """
    import pyotp, qrcode, io, base64 as _b64

    # Générer un nouveau secret (32 chars base32)
    secret = pyotp.random_base32()
    # Stocker le secret temporairement (pas encore activé)
    current_user.mfa_secret = secret
    db.commit()

    # URI pour l'authenticator
    totp = pyotp.TOTP(secret)
    display_name = current_user.first_name or current_user.email.split("@")[0]
    uri = totp.provisioning_uri(name=current_user.email, issuer_name="Wezea CyberHealth")

    # QR code PNG → base64
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = _b64.b64encode(buf.getvalue()).decode()

    return {
        "secret": secret,
        "uri": uri,
        "qr_base64": qr_b64,    # data:image/png;base64,<qr_base64>
        "display_name": display_name,
    }


@router.post("/2fa/verify")
def verify_2fa(
    body: TotpVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Vérifie le code TOTP et active la 2FA si elle ne l'est pas encore.
    Fenêtre de 1 intervalle (±30s) pour la tolérance d'horloge.
    """
    import pyotp

    if not current_user.mfa_secret:
        raise HTTPException(status_code=400, detail="Aucun secret 2FA configuré. Appelez /2fa/setup d'abord.")

    totp = pyotp.TOTP(current_user.mfa_secret)
    if not totp.verify(body.code.strip(), valid_window=1):
        raise HTTPException(status_code=400, detail="Code invalide ou expiré.")

    # Activer la 2FA
    current_user.mfa_enabled = True
    db.commit()
    return {"status": "ok", "mfa_enabled": True}


@router.post("/2fa/confirm-login")
def confirm_login_2fa(
    body: TotpVerifyRequest,
    db: Session = Depends(get_db),
):
    """
    Valide le code TOTP pendant le login (step=mfa).
    Le mfa_token est le JWT intermédiaire retourné par /auth/login quand mfa_required=True.
    Retourne un TokenResponse complet si le code est correct.
    """
    import pyotp
    from app.auth import decode_token, create_access_token

    if not body.mfa_token:
        raise HTTPException(status_code=400, detail="mfa_token manquant.")

    payload = decode_token(body.mfa_token)
    if not payload or payload.get("step") != "mfa":
        raise HTTPException(status_code=401, detail="Token MFA invalide ou expiré.")

    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable.")
    if not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(status_code=400, detail="2FA non activée sur ce compte.")

    totp = pyotp.TOTP(user.mfa_secret)
    if not totp.verify(body.code.strip(), valid_window=1):
        raise HTTPException(status_code=400, detail="Code invalide ou expiré.")

    # Émettre le vrai token d'accès
    token = create_access_token(user.id, user.email, user.plan)
    return TokenResponse(
        access_token=token,
        user={
            "id": user.id, "email": user.email, "plan": user.plan,
            "api_key": user.api_key, "first_name": user.first_name,
            "last_name": user.last_name, "google_id": user.google_id,
            "is_admin": bool(user.is_admin), "mfa_enabled": True,
        },
    )


@router.delete("/2fa/disable")
def disable_2fa(
    body: TotpDisableRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Désactive la 2FA après vérification du code TOTP + mot de passe.
    Interdit sur les comptes Google (pas de mot de passe local).
    """
    import pyotp

    # Bloquer les comptes Google (pas de mot de passe)
    if current_user.password_hash.startswith("!google:"):
        raise HTTPException(status_code=400, detail="Les comptes Google gèrent la 2FA via Google.")

    # Vérifier le mot de passe
    if not verify_password(body.password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Mot de passe incorrect.")

    # Vérifier le code TOTP
    if not current_user.mfa_enabled or not current_user.mfa_secret:
        raise HTTPException(status_code=400, detail="La 2FA n'est pas activée.")

    totp = pyotp.TOTP(current_user.mfa_secret)
    if not totp.verify(body.code.strip(), valid_window=1):
        raise HTTPException(status_code=400, detail="Code invalide ou expiré.")

    # Désactiver
    current_user.mfa_enabled = False
    current_user.mfa_secret  = None
    db.commit()
    return {"status": "ok", "mfa_enabled": False}
