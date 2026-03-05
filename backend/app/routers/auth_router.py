"""
Auth Router — Register, Login, Me, Profile (RGPD), Delete Account, Regenerate API Key, White-label
"""

import re
import time

from collections import defaultdict
from typing import Optional

import base64
import re as _re
from fastapi import APIRouter, Depends, HTTPException, Request, status, Header, BackgroundTasks, UploadFile, File
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

from app.auth import (
    hash_password, verify_password,
    create_access_token, decode_token,
    generate_api_key,
)
import os
from app.database import get_db
from app.limiter import limiter
from app.models import User
from app.services.brevo_service import (
    send_welcome_email,
    add_registered_user_contact,
    update_brevo_contact,
    delete_brevo_contact,
)
import asyncio

# ─── Login lockout (in-memory, par IP) ────────────────────────────────────────
_LOCKOUT_WINDOW = 15 * 60   # 15 minutes en secondes
_LOCKOUT_MAX    = 5         # échecs consécutifs avant verrouillage
_login_failures: dict[str, list[float]] = defaultdict(list)  # ip → timestamps


def _check_lockout(ip: str) -> None:
    """Lève HTTP 429 si l'IP a trop d'échecs récents."""
    now    = time.monotonic()
    cutoff = now - _LOCKOUT_WINDOW
    _login_failures[ip] = [t for t in _login_failures[ip] if t > cutoff]
    if len(_login_failures[ip]) >= _LOCKOUT_MAX:
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives échouées. Réessayez dans 15 minutes.",
        )


def _record_failure(ip: str) -> None:
    _login_failures[ip].append(time.monotonic())


def _clear_failures(ip: str) -> None:
    _login_failures.pop(ip, None)

router = APIRouter(prefix="/auth", tags=["auth"])

PASSWORD_MIN = 8
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")


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


# ─── Dependency : get current user from Bearer token ─────────────────────────
def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_optional_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Returns user or None — for endpoints that work both logged in and anonymous."""
    if not authorization or not authorization.startswith("Bearer "):
        # Try API key fallback
        return None
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    if not payload:
        return None
    return db.query(User).filter(User.id == int(payload["sub"])).first()


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
def register(
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


@router.post("/login", response_model=TokenResponse)
def login(request: Request, req: LoginRequest, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    _check_lockout(ip)

    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        _record_failure(ip)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    _clear_failures(ip)
    token = create_access_token(user.id, user.email, user.plan)
    return TokenResponse(
        access_token=token,
        user={"id": user.id, "email": user.email, "plan": user.plan, "api_key": user.api_key,
              "first_name": user.first_name, "last_name": user.last_name, "google_id": user.google_id,
              "is_admin": bool(user.is_admin)},
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
    def _sync_brevo():
        asyncio.run(update_brevo_contact(
            current_user.email,
            current_user.first_name,
            current_user.last_name,
        ))
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
    Exige la confirmation du mot de passe.
    Supprime l'utilisateur ET tous ses scans (cascade via SQLAlchemy).
    """
    if not verify_password(req.password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Mot de passe incorrect")

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
def change_password(
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
def change_email(
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
def google_auth(
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
        raise HTTPException(status_code=401, detail=f"Token Google invalide : {exc}")

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
    if current_user.plan not in ("pro", "team"):
        raise HTTPException(status_code=403, detail="White-label réservé au plan Pro.")
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
    if current_user.plan not in ("pro", "team"):
        raise HTTPException(status_code=403, detail="White-label réservé au plan Pro.")

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
    if current_user.plan not in ("pro", "team"):
        raise HTTPException(status_code=403, detail="White-label réservé au plan Pro.")

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
    if current_user.plan not in ("pro", "team"):
        raise HTTPException(status_code=403, detail="White-label réservé au plan Pro.")
    current_user.wb_logo_b64 = None
    db.commit()
    return {"status": "ok", "has_logo": False}
