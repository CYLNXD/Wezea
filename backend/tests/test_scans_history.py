"""
Tests : scans_router (GET/DELETE/PATCH /scans/history/…) et public_router (badge, partage, stats)
--------------------------------------------------------------------------------------------------
Stratégie :
- Création des users + tokens en DB directement (_make_user) — pas de rate-limit
- Création des ScanHistory directement en DB (_make_scan)
- Export PDF mocké (weasyprint/report_service.generate_pdf)
"""
import json
import uuid as _uuid
from unittest.mock import patch

import pytest

from app.models import ScanHistory, User
from app.auth import hash_password, generate_api_key, create_access_token


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(db_session, plan: str = "starter") -> dict:
    """Crée un user en DB et retourne email/user/token."""
    email = f"{plan}-{_uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("TestPass123"),
        plan=plan,
        api_key=generate_api_key(),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(user.id, email, plan)
    return {"email": email, "user": user, "token": token}


def _make_scan(db_session, user_id: int, *, domain: str = "example.com",
               score: int = 75, risk: str = "moderate",
               public_share: bool = False) -> ScanHistory:
    """Crée un ScanHistory directement en DB."""
    findings = [
        {
            "title": "SSL OK",
            "category": "ssl",
            "severity": "info",
            "penalty": 0,
            "plain_explanation": "Certificate valid",
            "recommendation": "Keep it up",
            "technical_detail": "TLSv1.3",
        }
    ]
    details = {
        "dns_details": {"spf": {"status": "ok"}, "dmarc": {"status": "ok", "policy": "reject"}},
        "ssl_details": {"status": "valid", "tls_version": "TLSv1.3", "days_left": 90},
        "port_details": {"443": {"open": True}, "22": {"open": False}},
        "recommendations": [{"priority": "LOW", "text": "Enable HSTS"}],
        "subdomain_details": {},
        "vuln_details": {},
    }
    scan = ScanHistory(
        user_id=user_id,
        scan_uuid=str(_uuid.uuid4()),
        domain=domain,
        security_score=score,
        risk_level=risk,
        findings_count=len(findings),
        findings_json=json.dumps(findings),
        scan_details_json=json.dumps(details),
        scan_duration=1234.5,
        public_share=public_share,
    )
    db_session.add(scan)
    db_session.commit()
    db_session.refresh(scan)
    return scan


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# GET /scans/history
# ─────────────────────────────────────────────────────────────────────────────

class TestScanHistoryList:
    def test_empty_list_for_new_user(self, client, db_session):
        u = _make_user(db_session)
        resp = client.get("/scans/history", headers=_auth(u["token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["scans"] == []

    def test_returns_own_scans(self, client, db_session):
        u = _make_user(db_session)
        _make_scan(db_session, u["user"].id, domain="alpha.com")
        _make_scan(db_session, u["user"].id, domain="beta.com")
        resp = client.get("/scans/history", headers=_auth(u["token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        domains = {s["domain"] for s in data["scans"]}
        assert domains == {"alpha.com", "beta.com"}

    def test_does_not_leak_other_users_scans(self, client, db_session):
        u1 = _make_user(db_session)
        u2 = _make_user(db_session)
        _make_scan(db_session, u1["user"].id, domain="u1.com")
        _make_scan(db_session, u2["user"].id, domain="u2.com")

        resp1 = client.get("/scans/history", headers=_auth(u1["token"]))
        resp2 = client.get("/scans/history", headers=_auth(u2["token"]))

        domains1 = {s["domain"] for s in resp1.json()["scans"]}
        domains2 = {s["domain"] for s in resp2.json()["scans"]}
        assert domains1 == {"u1.com"}
        assert domains2 == {"u2.com"}

    def test_pagination_limit_and_offset(self, client, db_session):
        u = _make_user(db_session)
        for i in range(5):
            _make_scan(db_session, u["user"].id, domain=f"page{i}.com")

        resp = client.get("/scans/history?limit=2&offset=0", headers=_auth(u["token"]))
        data = resp.json()
        assert data["total"] == 5
        assert len(data["scans"]) == 2

        resp2 = client.get("/scans/history?limit=2&offset=4", headers=_auth(u["token"]))
        assert len(resp2.json()["scans"]) == 1

    def test_scan_has_public_share_field(self, client, db_session):
        u = _make_user(db_session)
        _make_scan(db_session, u["user"].id, public_share=True)
        resp = client.get("/scans/history", headers=_auth(u["token"]))
        scan = resp.json()["scans"][0]
        assert "public_share" in scan
        assert scan["public_share"] is True

    def test_unauthenticated_returns_401(self, client, db_session):
        resp = client.get("/scans/history")
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# GET /scans/history/{uuid}
# ─────────────────────────────────────────────────────────────────────────────

class TestScanDetail:
    def test_get_own_scan_returns_200(self, client, db_session):
        u = _make_user(db_session)
        scan = _make_scan(db_session, u["user"].id, domain="detail.com", score=82)
        resp = client.get(f"/scans/history/{scan.scan_uuid}", headers=_auth(u["token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert data["scan_uuid"] == scan.scan_uuid
        assert data["domain"] == "detail.com"
        assert data["security_score"] == 82
        assert "findings" in data
        assert "dns_details" in data
        assert "ssl_details" in data

    def test_unknown_uuid_returns_404(self, client, db_session):
        u = _make_user(db_session)
        resp = client.get(f"/scans/history/{_uuid.uuid4()}", headers=_auth(u["token"]))
        assert resp.status_code == 404

    def test_other_users_scan_returns_404(self, client, db_session):
        u1 = _make_user(db_session)
        u2 = _make_user(db_session)
        scan = _make_scan(db_session, u1["user"].id)
        # u2 ne doit pas voir le scan de u1
        resp = client.get(f"/scans/history/{scan.scan_uuid}", headers=_auth(u2["token"]))
        assert resp.status_code == 404

    def test_unauthenticated_returns_401(self, client, db_session):
        u = _make_user(db_session)
        scan = _make_scan(db_session, u["user"].id)
        resp = client.get(f"/scans/history/{scan.scan_uuid}")
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# GET /scans/history/{uuid}/export
# ─────────────────────────────────────────────────────────────────────────────

class TestExportScan:
    def test_export_json_returns_json_file(self, client, db_session):
        u = _make_user(db_session, "starter")
        scan = _make_scan(db_session, u["user"].id, domain="export.com", score=70)
        resp = client.get(
            f"/scans/history/{scan.scan_uuid}/export?format=json",
            headers=_auth(u["token"]),
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        assert "attachment" in resp.headers["content-disposition"]
        assert ".json" in resp.headers["content-disposition"]
        data = resp.json()
        assert data["domain"] == "export.com"
        assert data["security_score"] == 70
        assert "findings" in data

    def test_export_csv_returns_csv_file(self, client, db_session):
        u = _make_user(db_session, "starter")
        scan = _make_scan(db_session, u["user"].id, domain="csvtest.com")
        resp = client.get(
            f"/scans/history/{scan.scan_uuid}/export?format=csv",
            headers=_auth(u["token"]),
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert ".csv" in resp.headers["content-disposition"]
        # Vérifier l'en-tête CSV
        text = resp.text
        assert "domain" in text
        assert "security_score" in text
        assert "csvtest.com" in text

    def test_export_pdf_returns_pdf(self, client, db_session):
        u = _make_user(db_session, "starter")
        scan = _make_scan(db_session, u["user"].id, domain="pdftest.com")
        fake_pdf = b"%PDF-1.4 fake pdf bytes"
        with patch("app.services.report_service.generate_pdf", return_value=fake_pdf):
            resp = client.get(
                f"/scans/history/{scan.scan_uuid}/export?format=pdf",
                headers=_auth(u["token"]),
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content == fake_pdf

    def test_export_unknown_scan_returns_404(self, client, db_session):
        u = _make_user(db_session, "starter")
        resp = client.get(
            f"/scans/history/{_uuid.uuid4()}/export?format=json",
            headers=_auth(u["token"]),
        )
        assert resp.status_code == 404

    def test_export_other_users_scan_returns_404(self, client, db_session):
        u1 = _make_user(db_session)
        u2 = _make_user(db_session)
        scan = _make_scan(db_session, u1["user"].id)
        resp = client.get(
            f"/scans/history/{scan.scan_uuid}/export?format=json",
            headers=_auth(u2["token"]),
        )
        assert resp.status_code == 404

    def test_export_invalid_format_returns_422(self, client, db_session):
        u = _make_user(db_session)
        scan = _make_scan(db_session, u["user"].id)
        resp = client.get(
            f"/scans/history/{scan.scan_uuid}/export?format=xml",
            headers=_auth(u["token"]),
        )
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /scans/history/{uuid}/share
# ─────────────────────────────────────────────────────────────────────────────

class TestToggleShare:
    def test_toggle_on_sets_public_share_true(self, client, db_session):
        u = _make_user(db_session)
        scan = _make_scan(db_session, u["user"].id, public_share=False)
        resp = client.patch(
            f"/scans/history/{scan.scan_uuid}/share",
            headers=_auth(u["token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["public_share"] is True
        assert data["scan_uuid"] == scan.scan_uuid

    def test_toggle_off_sets_public_share_false(self, client, db_session):
        u = _make_user(db_session)
        scan = _make_scan(db_session, u["user"].id, public_share=True)
        resp = client.patch(
            f"/scans/history/{scan.scan_uuid}/share",
            headers=_auth(u["token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["public_share"] is False

    def test_double_toggle_restores_original(self, client, db_session):
        u = _make_user(db_session)
        scan = _make_scan(db_session, u["user"].id, public_share=False)
        client.patch(f"/scans/history/{scan.scan_uuid}/share", headers=_auth(u["token"]))
        resp = client.patch(f"/scans/history/{scan.scan_uuid}/share", headers=_auth(u["token"]))
        assert resp.json()["public_share"] is False

    def test_toggle_unknown_scan_returns_404(self, client, db_session):
        u = _make_user(db_session)
        resp = client.patch(
            f"/scans/history/{_uuid.uuid4()}/share",
            headers=_auth(u["token"]),
        )
        assert resp.status_code == 404

    def test_toggle_other_users_scan_returns_404(self, client, db_session):
        u1 = _make_user(db_session)
        u2 = _make_user(db_session)
        scan = _make_scan(db_session, u1["user"].id)
        resp = client.patch(
            f"/scans/history/{scan.scan_uuid}/share",
            headers=_auth(u2["token"]),
        )
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /scans/history/{uuid}
# ─────────────────────────────────────────────────────────────────────────────

class TestDeleteScan:
    def test_delete_own_scan_returns_204(self, client, db_session):
        u = _make_user(db_session)
        scan = _make_scan(db_session, u["user"].id)
        resp = client.delete(
            f"/scans/history/{scan.scan_uuid}",
            headers=_auth(u["token"]),
        )
        assert resp.status_code == 204

    def test_deleted_scan_no_longer_accessible(self, client, db_session):
        u = _make_user(db_session)
        scan = _make_scan(db_session, u["user"].id)
        client.delete(f"/scans/history/{scan.scan_uuid}", headers=_auth(u["token"]))
        resp = client.get(f"/scans/history/{scan.scan_uuid}", headers=_auth(u["token"]))
        assert resp.status_code == 404

    def test_delete_unknown_scan_returns_404(self, client, db_session):
        u = _make_user(db_session)
        resp = client.delete(
            f"/scans/history/{_uuid.uuid4()}",
            headers=_auth(u["token"]),
        )
        assert resp.status_code == 404

    def test_delete_other_users_scan_returns_404(self, client, db_session):
        u1 = _make_user(db_session)
        u2 = _make_user(db_session)
        scan = _make_scan(db_session, u1["user"].id)
        resp = client.delete(
            f"/scans/history/{scan.scan_uuid}",
            headers=_auth(u2["token"]),
        )
        assert resp.status_code == 404
        # Le scan de u1 doit toujours exister
        resp_check = client.get(
            f"/scans/history/{scan.scan_uuid}",
            headers=_auth(u1["token"]),
        )
        assert resp_check.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# GET /public/badge/{domain}
# ─────────────────────────────────────────────────────────────────────────────

class TestPublicBadge:
    def test_badge_known_domain_returns_svg(self, client, db_session):
        u = _make_user(db_session)
        _make_scan(db_session, u["user"].id, domain="badge.com", score=85)
        resp = client.get("/public/badge/badge.com")
        assert resp.status_code == 200
        assert "image/svg+xml" in resp.headers["content-type"]
        assert b"<svg" in resp.content
        assert b"85" in resp.content

    def test_badge_unknown_domain_returns_question_mark(self, client, db_session):
        resp = client.get("/public/badge/never-scanned-xyz123.com")
        assert resp.status_code == 200
        assert b"?" in resp.content

    def test_badge_strips_www(self, client, db_session):
        u = _make_user(db_session)
        _make_scan(db_session, u["user"].id, domain="strip.com", score=60)
        # Requête avec www. — doit retourner le score du domaine sans www
        resp = client.get("/public/badge/www.strip.com")
        assert resp.status_code == 200
        assert b"60" in resp.content

    def test_badge_score_header_present(self, client, db_session):
        u = _make_user(db_session)
        _make_scan(db_session, u["user"].id, domain="header-test.com", score=72)
        resp = client.get("/public/badge/header-test.com")
        assert resp.headers.get("x-score") == "72"

    def test_badge_cache_control_header(self, client, db_session):
        resp = client.get("/public/badge/any-domain.com")
        assert "max-age" in resp.headers.get("cache-control", "")


# ─────────────────────────────────────────────────────────────────────────────
# GET /public/scan/{uuid}
# ─────────────────────────────────────────────────────────────────────────────

class TestPublicScan:
    def test_shared_scan_accessible_without_auth(self, client, db_session):
        u = _make_user(db_session)
        scan = _make_scan(db_session, u["user"].id, domain="shared.com", public_share=True)
        resp = client.get(f"/public/scan/{scan.scan_uuid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["domain"] == "shared.com"
        assert data["scan_uuid"] == scan.scan_uuid
        assert "findings" in data
        assert "dns_details" in data

    def test_private_scan_returns_403(self, client, db_session):
        u = _make_user(db_session)
        scan = _make_scan(db_session, u["user"].id, public_share=False)
        resp = client.get(f"/public/scan/{scan.scan_uuid}")
        assert resp.status_code == 403

    def test_unknown_uuid_returns_404(self, client, db_session):
        resp = client.get(f"/public/scan/{_uuid.uuid4()}")
        assert resp.status_code == 404

    def test_after_unshare_returns_403(self, client, db_session):
        u = _make_user(db_session)
        scan = _make_scan(db_session, u["user"].id, public_share=True)
        # Désactiver le partage
        client.patch(f"/scans/history/{scan.scan_uuid}/share", headers=_auth(u["token"]))
        # Le lien public doit retourner 403
        resp = client.get(f"/public/scan/{scan.scan_uuid}")
        assert resp.status_code == 403

    def test_share_then_public_access_works(self, client, db_session):
        u = _make_user(db_session)
        scan = _make_scan(db_session, u["user"].id, public_share=False)
        # Activer le partage
        client.patch(f"/scans/history/{scan.scan_uuid}/share", headers=_auth(u["token"]))
        # Le lien public doit fonctionner
        resp = client.get(f"/public/scan/{scan.scan_uuid}")
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# GET /public/stats
# ─────────────────────────────────────────────────────────────────────────────

class TestPublicStats:
    def test_stats_returns_zero_for_empty_db(self, client, db_session):
        resp = client.get("/public/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_scans" in data
        assert "estimated_vulns" in data
        assert data["total_scans"] == 0

    def test_stats_counts_scans(self, client, db_session):
        u = _make_user(db_session)
        _make_scan(db_session, u["user"].id)
        _make_scan(db_session, u["user"].id)
        resp = client.get("/public/stats")
        data = resp.json()
        assert data["total_scans"] == 2
        assert data["estimated_vulns"] == 8  # 2 * 4

    def test_stats_no_auth_required(self, client, db_session):
        # Pas de header Authorization
        resp = client.get("/public/stats")
        assert resp.status_code == 200


class TestExportScanEdgeCases:
    """Chemins non couverts dans scans_router.py — export PDF."""

    def test_export_pdf_runtime_error_returns_503(self, client, db_session):
        """generate_pdf lève RuntimeError (WeasyPrint absent) → 503."""
        u = _make_user(db_session, "starter")
        scan = _make_scan(db_session, u["user"].id, domain="503test.com")
        with patch("app.services.report_service.generate_pdf",
                   side_effect=RuntimeError("WeasyPrint not available")):
            resp = client.get(
                f"/scans/history/{scan.scan_uuid}/export?format=pdf",
                headers=_auth(u["token"]),
            )
        assert resp.status_code == 503

    def test_export_pdf_unexpected_exception_returns_500(self, client, db_session):
        """generate_pdf lève Exception générique → 500."""
        u = _make_user(db_session, "starter")
        scan = _make_scan(db_session, u["user"].id, domain="500test.com")
        with patch("app.services.report_service.generate_pdf",
                   side_effect=Exception("unexpected crash")):
            resp = client.get(
                f"/scans/history/{scan.scan_uuid}/export?format=pdf",
                headers=_auth(u["token"]),
            )
        assert resp.status_code == 500

    def test_export_pdf_with_white_label(self, client, db_session):
        """Export PDF : white-label injecté pour les utilisateurs Pro avec wb_enabled."""
        u = _make_user(db_session, "pro")
        # Activer le white-label
        from app.models import User
        db_user = db_session.query(User).filter_by(id=u["user"].id).first()
        db_user.wb_enabled      = True
        db_user.wb_company_name = "AcmeCorp"
        db_user.wb_primary_color = "#ff0000"
        db_session.commit()

        scan     = _make_scan(db_session, u["user"].id, domain="wltest.com")
        fake_pdf = b"%PDF-1.4 white-label"

        captured = {}

        def _fake_pdf(audit_data, lang, white_label=None):
            captured["white_label"] = white_label
            return fake_pdf

        with patch("app.services.report_service.generate_pdf", side_effect=_fake_pdf):
            resp = client.get(
                f"/scans/history/{scan.scan_uuid}/export?format=pdf",
                headers=_auth(u["token"]),
            )

        assert resp.status_code == 200
        assert captured.get("white_label") is not None
        assert captured["white_label"]["company_name"] == "AcmeCorp"
