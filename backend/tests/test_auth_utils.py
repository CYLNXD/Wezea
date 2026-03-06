"""
Tests unitaires pour app.auth (fonctions pures JWT / password / API key)
et app.services.brevo_service (helpers purs _esc, _base_html).

Zéro appel réseau, zéro DB — fonctions déterministes uniquement.
"""
from __future__ import annotations

import time
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# hash_password / verify_password / needs_rehash
# ─────────────────────────────────────────────────────────────────────────────

class TestHashPassword:

    def test_returns_string(self):
        from app.auth import hash_password
        h = hash_password("secret")
        assert isinstance(h, str)

    def test_produces_argon2_hash(self):
        """Le hash par défaut doit commencer par $argon2."""
        from app.auth import hash_password
        h = hash_password("MyPassword123")
        assert h.startswith("$argon2"), f"Expected argon2 hash, got: {h[:20]}"

    def test_different_hashes_for_same_password(self):
        """Chaque appel produit un hash différent (salt aléatoire)."""
        from app.auth import hash_password
        h1 = hash_password("password")
        h2 = hash_password("password")
        assert h1 != h2

    def test_hash_not_plaintext(self):
        from app.auth import hash_password
        h = hash_password("secret123")
        assert "secret123" not in h


class TestVerifyPassword:

    def test_correct_password_returns_true(self):
        from app.auth import hash_password, verify_password
        h = hash_password("correct")
        assert verify_password("correct", h) is True

    def test_wrong_password_returns_false(self):
        from app.auth import hash_password, verify_password
        h = hash_password("correct")
        assert verify_password("wrong", h) is False

    def test_empty_password_returns_false(self):
        from app.auth import hash_password, verify_password
        h = hash_password("correct")
        assert verify_password("", h) is False

    def test_garbage_hash_returns_false(self):
        """Un hash invalide ne doit pas lever d'exception — retourner False."""
        from app.auth import verify_password
        assert verify_password("anything", "not-a-valid-hash") is False

    def test_empty_hash_returns_false(self):
        from app.auth import verify_password
        assert verify_password("password", "") is False

    def test_case_sensitive(self):
        """Le mot de passe est sensible à la casse."""
        from app.auth import hash_password, verify_password
        h = hash_password("Password")
        assert verify_password("password", h) is False
        assert verify_password("PASSWORD", h) is False
        assert verify_password("Password", h) is True


class TestNeedsRehash:

    def test_argon2_hash_does_not_need_rehash(self):
        """Un hash argon2 fraîchement généré ne nécessite pas de rehash."""
        from app.auth import hash_password, needs_rehash
        h = hash_password("test")
        assert needs_rehash(h) is False

    def test_invalid_hash_returns_false(self):
        """Un hash invalide ne doit pas lever d'exception."""
        from app.auth import needs_rehash
        assert needs_rehash("garbage") is False

    def test_empty_hash_returns_false(self):
        from app.auth import needs_rehash
        assert needs_rehash("") is False


# ─────────────────────────────────────────────────────────────────────────────
# create_access_token / decode_token
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateAccessToken:

    def test_returns_string(self):
        from app.auth import create_access_token
        token = create_access_token(1, "test@example.com", "free")
        assert isinstance(token, str)
        assert len(token) > 20

    def test_token_has_three_jwt_segments(self):
        """Un JWT valide contient 3 segments séparés par des points."""
        from app.auth import create_access_token
        token = create_access_token(1, "test@example.com", "free")
        assert token.count(".") == 2

    def test_payload_contains_expected_fields(self):
        from app.auth import create_access_token, decode_token
        token = create_access_token(42, "user@example.com", "pro")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "42"
        assert payload["email"] == "user@example.com"
        assert payload["plan"] == "pro"

    def test_token_expires_in_future(self):
        from app.auth import create_access_token, decode_token
        token = create_access_token(1, "a@a.com", "free")
        payload = decode_token(token)
        assert payload["exp"] > time.time()

    def test_different_users_produce_different_tokens(self):
        from app.auth import create_access_token
        t1 = create_access_token(1, "a@a.com", "free")
        t2 = create_access_token(2, "b@b.com", "pro")
        assert t1 != t2

    def test_sub_is_string_not_int(self):
        """Le claim 'sub' doit être une chaîne (JWT spec)."""
        from app.auth import create_access_token, decode_token
        token = create_access_token(99, "x@x.com", "free")
        payload = decode_token(token)
        assert isinstance(payload["sub"], str)


class TestDecodeToken:

    def test_valid_token_returns_payload(self):
        from app.auth import create_access_token, decode_token
        token = create_access_token(7, "x@x.com", "starter")
        payload = decode_token(token)
        assert payload is not None
        assert payload["email"] == "x@x.com"

    def test_invalid_token_returns_none(self):
        from app.auth import decode_token
        assert decode_token("not.a.token") is None

    def test_empty_string_returns_none(self):
        from app.auth import decode_token
        assert decode_token("") is None

    def test_tampered_signature_returns_none(self):
        """Modifier la signature doit invalider le token."""
        from app.auth import create_access_token, decode_token
        token = create_access_token(1, "a@a.com", "free")
        # Remplace le dernier caractère pour casser la signature
        tampered = token[:-1] + ("X" if token[-1] != "X" else "Y")
        assert decode_token(tampered) is None

    def test_random_string_returns_none(self):
        from app.auth import decode_token
        assert decode_token("eyJhbGciOiJSUzI1NiJ9.garbage.badsig") is None


# ─────────────────────────────────────────────────────────────────────────────
# generate_api_key
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateApiKey:

    def test_starts_with_wsk_prefix(self):
        from app.auth import generate_api_key
        key = generate_api_key()
        assert key.startswith("wsk_")

    def test_sufficient_length(self):
        """La clé doit faire au moins 40 caractères (wsk_ + 32+ chars)."""
        from app.auth import generate_api_key
        key = generate_api_key()
        assert len(key) >= 40

    def test_keys_are_unique(self):
        """Deux appels successifs produisent des clés différentes."""
        from app.auth import generate_api_key
        keys = {generate_api_key() for _ in range(10)}
        assert len(keys) == 10

    def test_key_is_url_safe(self):
        """La partie après le préfixe ne doit contenir que des chars URL-safe."""
        import re
        from app.auth import generate_api_key
        key = generate_api_key()
        suffix = key[4:]  # retire "wsk_"
        assert re.match(r'^[A-Za-z0-9_-]+$', suffix), f"Non-URL-safe chars in: {suffix}"


# ─────────────────────────────────────────────────────────────────────────────
# brevo_service._esc (helper HTML-escape pur)
# ─────────────────────────────────────────────────────────────────────────────

class TestBrEsc:
    """Tests pour app.services.brevo_service._esc (HTML escape)."""

    def test_plain_string_unchanged(self):
        from app.services.brevo_service import _esc
        assert _esc("hello") == "hello"

    def test_escapes_angle_brackets(self):
        from app.services.brevo_service import _esc
        assert "<script>" not in _esc("<script>")
        assert "&lt;script&gt;" == _esc("<script>")

    def test_escapes_ampersand(self):
        from app.services.brevo_service import _esc
        assert _esc("A&B") == "A&amp;B"

    def test_escapes_double_quote(self):
        from app.services.brevo_service import _esc
        result = _esc('"quoted"')
        assert '"' not in result
        assert "&quot;" in result

    def test_converts_non_string_to_string(self):
        """_esc accepte n'importe quelle valeur et la convertit en str."""
        from app.services.brevo_service import _esc
        assert _esc(42) == "42"
        assert _esc(None) == "None"

    def test_empty_string(self):
        from app.services.brevo_service import _esc
        assert _esc("") == ""

    def test_xss_payload_sanitized(self):
        """Un payload XSS classique doit être neutralisé."""
        from app.services.brevo_service import _esc
        payload = '<img src=x onerror=alert(1)>'
        escaped = _esc(payload)
        assert "<img" not in escaped
        assert "alert" in escaped   # le texte reste mais les balises sont échappées
        assert "&lt;" in escaped
