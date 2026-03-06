"""
Tests : validation des domaines (SSRF, format, nettoyage)
Ces tests vérifient uniquement la couche de validation Pydantic —
aucun scan réseau réel n'est effectué.
"""
import pytest
from app.main import ScanRequest
from pydantic import ValidationError


# ─────────────────────────────────────────────────────────────────────────────
# Domaines valides (doivent passer la validation)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("domain,expected", [
    ("example.com",                 "example.com"),
    ("EXAMPLE.COM",                 "example.com"),       # normalisation lowercase
    ("sub.example.co.uk",           "sub.example.co.uk"),
    ("http://example.com",          "example.com"),       # strip du schéma http
    ("https://example.com",         "example.com"),       # strip du schéma https
    ("https://example.com/path",    "example.com"),       # strip du chemin
    ("www.example.com",             "example.com"),       # strip www
    ("my-startup.io",               "my-startup.io"),
    ("wezea.net",                   "wezea.net"),
])
def test_valid_domain(domain, expected):
    req = ScanRequest(domain=domain)
    assert req.domain == expected


# ─────────────────────────────────────────────────────────────────────────────
# Domaines bloqués (SSRF / adresses privées)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("blocked", [
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "metadata.google.internal",
    "10.0.0.1",
    "192.168.1.1",
    "172.16.0.1",
    "172.31.255.255",
    "169.254.169.254",    # AWS IMDS — critique SSRF
])
def test_blocked_domain_raises(blocked):
    with pytest.raises(ValidationError) as exc_info:
        ScanRequest(domain=blocked)
    errors = exc_info.value.errors()
    assert any("domain" in str(e["loc"]) for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# Domaines invalides (format incorrect)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("invalid", [
    "",
    "   ",
    "not_a_domain",          # underscore interdit
    "-startswith-dash.com",  # commence par un tiret
    "a" * 254 + ".com",      # trop long (> 253 chars)
    "no-tld",                # pas de TLD
    "double..dot.com",       # double point
])
def test_invalid_domain_raises(invalid):
    with pytest.raises(ValidationError):
        ScanRequest(domain=invalid)


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint /scan — validation HTTP (retourne 422 sans lancer de scan)
# ─────────────────────────────────────────────────────────────────────────────

def test_scan_endpoint_rejects_localhost(client):
    resp = client.post("/scan", json={"domain": "localhost"})
    assert resp.status_code == 422


def test_scan_endpoint_rejects_private_ip(client):
    resp = client.post("/scan", json={"domain": "192.168.1.1"})
    assert resp.status_code == 422


def test_scan_endpoint_rejects_empty_domain(client):
    resp = client.post("/scan", json={"domain": ""})
    assert resp.status_code == 422


def test_scan_endpoint_rejects_aws_imds(client):
    """169.254.169.254 = AWS Instance Metadata — SSRF critique."""
    resp = client.post("/scan", json={"domain": "169.254.169.254"})
    assert resp.status_code == 422
