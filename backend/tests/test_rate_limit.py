"""
Tests : rate limiting des scans
- Vérification que le comportement du compteur est correct
- Les scans réels sont mockés (pas de réseau)
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.models import ScanRateLimit


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mock_scan_result():
    """Retourne un faux résultat de scan pour éviter les appels réseau."""
    result = MagicMock()
    result.security_score = 75
    result.risk_level = "low"
    result.findings = []
    result.dns_details = {}
    result.ssl_details = {}
    result.port_details = {}
    result.recommendations = []
    result.subdomain_details = {}
    result.vuln_details = {}
    result.scan_duration_ms = 100
    result.to_dict.return_value = {
        "scan_id": "test-uuid",
        "domain": "test.com",
        "scanned_at": "2026-01-01T00:00:00Z",
        "security_score": 75,
        "risk_level": "low",
        "findings": [],
        "dns_details": {},
        "ssl_details": {},
        "port_details": {},
        "recommendations": [],
        "subdomain_details": {},
        "vuln_details": {},
        "scan_duration_ms": 100,
        "meta": {},
    }
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Rate limit : table ScanRateLimit
# ─────────────────────────────────────────────────────────────────────────────

def test_scan_rate_limit_model(db_session):
    """Vérifie que la table ScanRateLimit fonctionne correctement."""
    entry = ScanRateLimit(
        client_id="test-cookie-123",
        date_key="2026-01-01",
        scan_count=1,
    )
    db_session.add(entry)
    db_session.flush()

    fetched = db_session.query(ScanRateLimit).filter_by(client_id="test-cookie-123").first()
    assert fetched is not None
    assert fetched.scan_count == 1


def test_scan_rate_limit_increment(db_session):
    """Simule l'incrémentation du compteur de scans."""
    client_id = "test-cookie-increment"
    date_key = "2026-01-01"

    entry = ScanRateLimit(client_id=client_id, date_key=date_key, scan_count=0)
    db_session.add(entry)
    db_session.flush()

    # Simuler un incrément
    entry.scan_count += 1
    db_session.flush()

    fetched = db_session.query(ScanRateLimit).filter_by(client_id=client_id, date_key=date_key).first()
    assert fetched.scan_count == 1


def test_scan_rate_limit_different_days(db_session):
    """Les compteurs par jour sont indépendants (reset quotidien)."""
    client_id = "test-cookie-days"

    db_session.add(ScanRateLimit(client_id=client_id, date_key="2026-01-01", scan_count=5))
    db_session.add(ScanRateLimit(client_id=client_id, date_key="2026-01-02", scan_count=2))
    db_session.flush()

    day1 = db_session.query(ScanRateLimit).filter_by(client_id=client_id, date_key="2026-01-01").first()
    day2 = db_session.query(ScanRateLimit).filter_by(client_id=client_id, date_key="2026-01-02").first()

    assert day1.scan_count == 5
    assert day2.scan_count == 2
    assert day1.scan_count != day2.scan_count


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint /scan/limits — vérifie la réponse
# ─────────────────────────────────────────────────────────────────────────────

def test_scan_limits_anonymous(client):
    """/scan/limits retourne les limites pour un utilisateur anonyme."""
    resp = client.get("/scan/limits")
    assert resp.status_code == 200
    data = resp.json()
    # Les champs doivent être présents
    assert "limit" in data or "remaining" in data or "used" in data


def test_scan_limits_authenticated(client, registered_user):
    """/scan/limits retourne les limites pour un utilisateur connecté."""
    resp = client.get("/scan/limits", headers={
        "Authorization": f"Bearer {registered_user['token']}"
    })
    assert resp.status_code == 200
