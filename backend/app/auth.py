"""
Auth utilities — JWT, password hashing, API key generation
"""
from __future__ import annotations

import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

# ─── Config ───────────────────────────────────────────────────────────────────

_raw_secret = os.getenv("JWT_SECRET_KEY", "")

if not _raw_secret or len(_raw_secret) < 32:
    # Génère un secret aléatoire pour cette session (⚠ invalide les JWT existants à chaque restart)
    # → Configurez JWT_SECRET_KEY dans .env pour éviter ce comportement : openssl rand -hex 32
    _generated = secrets.token_urlsafe(48)
    print(
        "⚠  AVERTISSEMENT SÉCURITÉ : JWT_SECRET_KEY absent ou trop court.\n"
        f"   Un secret temporaire a été généré pour cette session.\n"
        f"   Ajoutez dans .env : JWT_SECRET_KEY={_generated}\n"
        "   (les utilisateurs seront déconnectés à chaque redémarrage tant que cette variable manque)",
        file=sys.stderr,
    )
    _raw_secret = _generated

SECRET_KEY      = _raw_secret
ALGORITHM       = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES  = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 24h

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ─── Password ─────────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ─── JWT ──────────────────────────────────────────────────────────────────────
def create_access_token(user_id: int, email: str, plan: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "email": email,
        "plan": plan,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


# ─── API Key ──────────────────────────────────────────────────────────────────
def generate_api_key() -> str:
    return "wsk_" + secrets.token_urlsafe(32)
