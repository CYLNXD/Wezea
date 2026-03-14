"""
Tests — compliance_router.py endpoints
========================================
GET   /compliance/report?domain=X&lang=fr
GET   /compliance/checklist?domain=X
PATCH /compliance/checklist
"""
import json
import uuid

import pytest

from app.auth import create_access_token, hash_password
from app.compliance_mapper import ORGANIZATIONAL_ITEMS
from app.models import ComplianceChecklist, ScanHistory, User


def _make_user(db_session, plan="starter"):
    email = f"comp-{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash=hash_password("Test123"), plan=plan)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _auth(user):
    token = create_access_token(user.id, user.email, user.plan)
    return {"Authorization": f"Bearer {token}"}


def _add_scan(db_session, user, domain="test.com", score=75, findings=None):
    """Ajoute un scan avec des findings optionnels."""
    details = {"findings": findings or []}
    scan = ScanHistory(
        user_id=user.id,
        scan_uuid=uuid.uuid4().hex,
        domain=domain,
        security_score=score,
        risk_level="MEDIUM",
        findings_count=len(findings or []),
        scan_details_json=json.dumps(details),
    )
    db_session.add(scan)
    db_session.commit()
    return scan


# ── GET /compliance/report ──────────────────────────────────────────────────────


class TestComplianceReport:
    def test_report_without_scan(self, client, db_session):
        user = _make_user(db_session)
        resp = client.get("/compliance/report", params={"domain": "noscan.com"}, headers=_auth(user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_scan"] is False
        assert data["domain"] == "noscan.com"
        assert "nis2_score" in data
        assert "rgpd_score" in data
        assert "organizational_items" in data
        assert len(data["organizational_items"]) == 8

    def test_report_with_scan(self, client, db_session):
        user = _make_user(db_session)
        findings = [
            {"category": "DNS", "title": "SPF manquant", "severity": "HIGH"},
        ]
        _add_scan(db_session, user, domain="scanned.com", findings=findings)
        resp = client.get("/compliance/report", params={"domain": "scanned.com"}, headers=_auth(user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_scan"] is True
        assert data["domain"] == "scanned.com"

    def test_report_progress_counters(self, client, db_session):
        user = _make_user(db_session)
        resp = client.get("/compliance/report", params={"domain": "x.com"}, headers=_auth(user))
        data = resp.json()
        progress = data["progress"]
        assert "tech_total" in progress
        assert "tech_pass" in progress
        assert "org_total" in progress
        assert progress["org_total"] == 8
        assert progress["org_pass"] == 0  # no items checked
        assert progress["total"] == progress["tech_total"] + progress["org_total"]

    def test_report_org_items_reflect_checked(self, client, db_session):
        user = _make_user(db_session)
        # Check one item
        item = ComplianceChecklist(
            user_id=user.id, domain="y.com", item_id="org_mfa", checked=True,
        )
        db_session.add(item)
        db_session.commit()

        resp = client.get("/compliance/report", params={"domain": "y.com"}, headers=_auth(user))
        data = resp.json()
        mfa = next(i for i in data["organizational_items"] if i["id"] == "org_mfa")
        assert mfa["checked"] is True
        assert data["progress"]["org_pass"] == 1

    def test_report_requires_auth(self, client):
        resp = client.get("/compliance/report", params={"domain": "x.com"})
        assert resp.status_code == 401

    def test_report_lang_en(self, client, db_session):
        user = _make_user(db_session)
        resp = client.get("/compliance/report", params={"domain": "z.com", "lang": "en"}, headers=_auth(user))
        data = resp.json()
        # Org items should be in English
        item = data["organizational_items"][0]
        assert item["label"]  # non-empty


# ── GET /compliance/checklist ───────────────────────────────────────────────────


class TestComplianceChecklist:
    def test_checklist_empty(self, client, db_session):
        user = _make_user(db_session, plan="starter")
        resp = client.get("/compliance/checklist", params={"domain": "a.com"}, headers=_auth(user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["domain"] == "a.com"
        assert len(data["items"]) == 8
        assert all(not item["checked"] for item in data["items"])

    def test_checklist_with_checked_items(self, client, db_session):
        user = _make_user(db_session, plan="starter")
        from datetime import datetime, timezone
        item = ComplianceChecklist(
            user_id=user.id, domain="b.com", item_id="org_backup", checked=True, notes="S3 daily",
            checked_at=datetime.now(timezone.utc),
        )
        db_session.add(item)
        db_session.commit()

        resp = client.get("/compliance/checklist", params={"domain": "b.com"}, headers=_auth(user))
        data = resp.json()
        backup = next(i for i in data["items"] if i["id"] == "org_backup")
        assert backup["checked"] is True
        assert backup["notes"] == "S3 daily"
        assert backup["checked_at"] is not None

    def test_checklist_requires_paid(self, client, db_session):
        user = _make_user(db_session, plan="free")
        resp = client.get("/compliance/checklist", params={"domain": "c.com"}, headers=_auth(user))
        assert resp.status_code == 403

    def test_checklist_isolation_between_domains(self, client, db_session):
        user = _make_user(db_session, plan="pro")
        item = ComplianceChecklist(
            user_id=user.id, domain="d1.com", item_id="org_mfa", checked=True,
        )
        db_session.add(item)
        db_session.commit()

        resp = client.get("/compliance/checklist", params={"domain": "d2.com"}, headers=_auth(user))
        data = resp.json()
        mfa = next(i for i in data["items"] if i["id"] == "org_mfa")
        assert mfa["checked"] is False  # different domain

    def test_checklist_isolation_between_users(self, client, db_session):
        user1 = _make_user(db_session, plan="starter")
        user2 = _make_user(db_session, plan="starter")
        item = ComplianceChecklist(
            user_id=user1.id, domain="shared.com", item_id="org_training", checked=True,
        )
        db_session.add(item)
        db_session.commit()

        resp = client.get("/compliance/checklist", params={"domain": "shared.com"}, headers=_auth(user2))
        data = resp.json()
        training = next(i for i in data["items"] if i["id"] == "org_training")
        assert training["checked"] is False  # different user


# ── PATCH /compliance/checklist ─────────────────────────────────────────────────


class TestChecklistToggle:
    def test_toggle_on(self, client, db_session):
        user = _make_user(db_session, plan="starter")
        resp = client.patch("/compliance/checklist", json={
            "domain": "e.com", "item_id": "org_incident_plan", "checked": True,
        }, headers=_auth(user))
        assert resp.status_code == 200
        assert resp.json()["checked"] is True

        # Verify in DB
        item = db_session.query(ComplianceChecklist).filter_by(
            user_id=user.id, domain="e.com", item_id="org_incident_plan"
        ).first()
        assert item is not None
        assert item.checked is True
        assert item.checked_at is not None

    def test_toggle_off(self, client, db_session):
        user = _make_user(db_session, plan="starter")
        # First check
        client.patch("/compliance/checklist", json={
            "domain": "f.com", "item_id": "org_mfa", "checked": True,
        }, headers=_auth(user))
        # Then uncheck
        resp = client.patch("/compliance/checklist", json={
            "domain": "f.com", "item_id": "org_mfa", "checked": False,
        }, headers=_auth(user))
        assert resp.status_code == 200
        assert resp.json()["checked"] is False

        item = db_session.query(ComplianceChecklist).filter_by(
            user_id=user.id, domain="f.com", item_id="org_mfa"
        ).first()
        assert item.checked is False
        assert item.checked_at is None

    def test_toggle_with_notes(self, client, db_session):
        user = _make_user(db_session, plan="starter")
        resp = client.patch("/compliance/checklist", json={
            "domain": "g.com", "item_id": "org_backup", "checked": True, "notes": "AWS S3 + daily cron",
        }, headers=_auth(user))
        assert resp.status_code == 200

        item = db_session.query(ComplianceChecklist).filter_by(
            user_id=user.id, domain="g.com", item_id="org_backup"
        ).first()
        assert item.notes == "AWS S3 + daily cron"

    def test_toggle_upsert(self, client, db_session):
        """Second toggle on same item should update, not create duplicate."""
        user = _make_user(db_session, plan="pro")
        for i in range(3):
            client.patch("/compliance/checklist", json={
                "domain": "h.com", "item_id": "org_bcp", "checked": i % 2 == 0,
            }, headers=_auth(user))

        count = db_session.query(ComplianceChecklist).filter_by(
            user_id=user.id, domain="h.com", item_id="org_bcp"
        ).count()
        assert count == 1

    def test_toggle_invalid_item_id(self, client, db_session):
        user = _make_user(db_session, plan="starter")
        resp = client.patch("/compliance/checklist", json={
            "domain": "i.com", "item_id": "org_nonexistent", "checked": True,
        }, headers=_auth(user))
        assert resp.status_code == 400

    def test_toggle_requires_paid(self, client, db_session):
        user = _make_user(db_session, plan="free")
        resp = client.patch("/compliance/checklist", json={
            "domain": "j.com", "item_id": "org_mfa", "checked": True,
        }, headers=_auth(user))
        assert resp.status_code == 403

    def test_toggle_requires_auth(self, client):
        resp = client.patch("/compliance/checklist", json={
            "domain": "k.com", "item_id": "org_mfa", "checked": True,
        })
        assert resp.status_code == 401
