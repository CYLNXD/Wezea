"""
Auth utilities — JWT, password hashing, API key generation
──────────────────────────────────────────────────────────
Stratégie de hashing :
  - Nouveaux mots de passe   → argon2 (plus sécurisé, plus rapide que bcrypt)
  - Mots de passe existants  → bcrypt (lus et vérifiés, rehashés en argon2 au prochain login)
  - Rehash transparent       → géré dans auth_router.py via needs_rehash()

Pour migrer entièrement vers argon2 sur la production existante,
appeler rehash_if_needed() après chaque login réussi.
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

SECRET_KEY                  = _raw_secret
ALGORITHM                   = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 24h

# ─── Password context ─────────────────────────────────────────────────────────
#
# schemes = ["argon2", "bcrypt"]
#   - argon2  : algorithme par défaut pour les NOUVEAUX hashes
#   - bcrypt  : algorithme legacy, déprécié → détecté à la vérification
#
# deprecated = ["bcrypt"]
#   - needs_rehash(hash) retourne True si le hash est en bcrypt
#   - le re-hash en argon2 est effectué dans auth_router.login()
#
# Pré-requis : argon2-cffi==23.1.0 dans requirements.txt
# ─────────────────────────────────────────────────────────────────────────────
pwd_context = CryptContext(
    schemes     = ["argon2", "bcrypt"],
    deprecated  = ["bcrypt"],
)


# ─── Password ─────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash un mot de passe avec argon2 (algorithme par défaut)."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Vérifie un mot de passe (supporte argon2 et bcrypt legacy)."""
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def needs_rehash(hashed: str) -> bool:
    """
    Retourne True si le hash doit être migré (ex. bcrypt → argon2).
    À appeler après verify_password() réussi pour déclencher le rehash transparent.
    """
    try:
        return pwd_context.needs_update(hashed)
    except Exception:
        return False


# ─── JWT ──────────────────────────────────────────────────────────────────────

def create_access_token(user_id: int, email: str, plan: str, step: Optional[str] = None) -> str:
    """
    Génère un JWT.
    step="mfa" → token intermédiaire (durée 5 min) pour l'étape TOTP.
    """
    if step == "mfa":
        expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict = {
        "sub": str(user_id),
        "email": email,
        "plan": plan,
        "exp": expire,
    }
    if step:
        payload["step"] = step
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


def hash_api_key(key: str) -> str:
    """
    HMAC-SHA256 de la clé API avec SECRET_KEY.
    Permet le lookup en DB sans stocker la clé en clair.
    Déterministe : hash(key) == hash(key) → pas de sel aléatoire (contrairement aux mots de passe).
    """
    import hmac as _hmac
    import hashlib as _hashlib
    return _hmac.new(SECRET_KEY.encode(), key.encode(), _hashlib.sha256).hexdigest()


def mask_api_key(key: str) -> str:
    """
    Retourne un masque pour affichage (p. ex. wsk_AbCdEfGh...wxyz).
    Affiche les 12 premiers + 4 derniers caractères.
    """
    if len(key) <= 20:
        return key
    return key[:12] + "..." + key[-4:]
