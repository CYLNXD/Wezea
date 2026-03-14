"""
Tests — compliance_mapper ORGANIZATIONAL_ITEMS + ComplianceChecklist model
=========================================================================
"""
import pytest
from datetime import datetime, timezone

from app.compliance_mapper import ORGANIZATIONAL_ITEMS


# ── ORGANIZATIONAL_ITEMS intégrité ──────────────────────────────────────────────


class TestOrganizationalItems:
    """Vérifie la structure et la cohérence des items organisationnels."""

    def test_count(self):
        assert len(ORGANIZATIONAL_ITEMS) == 8

    def test_all_have_required_fields(self):
        required = {"id", "label_fr", "label_en", "desc_fr", "desc_en", "nis2_articles", "rgpd_articles"}
        for item in ORGANIZATIONAL_ITEMS:
            missing = required - set(item.keys())
            assert not missing, f"Item {item.get('id', '?')} missing: {missing}"

    def test_ids_unique(self):
        ids = [item["id"] for item in ORGANIZATIONAL_ITEMS]
        assert len(ids) == len(set(ids))

    def test_ids_start_with_org(self):
        for item in ORGANIZATIONAL_ITEMS:
            assert item["id"].startswith("org_"), f"{item['id']} ne commence pas par org_"

    def test_all_have_nis2_articles(self):
        for item in ORGANIZATIONAL_ITEMS:
            assert len(item["nis2_articles"]) >= 1, f"{item['id']} a 0 articles NIS2"

    def test_nis2_article_format(self):
        """NIS2 articles should be like '21-2-a', '21-2-b', etc."""
        for item in ORGANIZATIONAL_ITEMS:
            for art in item["nis2_articles"]:
                assert art.startswith("21-2-"), f"{item['id']}: article '{art}' invalide"

    def test_rgpd_articles_are_strings(self):
        for item in ORGANIZATIONAL_ITEMS:
            for art in item["rgpd_articles"]:
                assert isinstance(art, str)

    def test_known_items(self):
        ids = {item["id"] for item in ORGANIZATIONAL_ITEMS}
        expected = {
            "org_incident_plan", "org_training", "org_access_control", "org_mfa",
            "org_backup", "org_vendor_mgmt", "org_encryption_at_rest", "org_bcp",
        }
        assert ids == expected

    def test_labels_non_empty(self):
        for item in ORGANIZATIONAL_ITEMS:
            assert item["label_fr"].strip(), f"{item['id']} label_fr vide"
            assert item["label_en"].strip(), f"{item['id']} label_en vide"

    def test_descriptions_non_empty(self):
        for item in ORGANIZATIONAL_ITEMS:
            assert item["desc_fr"].strip(), f"{item['id']} desc_fr vide"
            assert item["desc_en"].strip(), f"{item['id']} desc_en vide"


# ── ComplianceChecklist model ───────────────────────────────────────────────────


class TestComplianceChecklistModel:
    """Teste le CRUD basique du modèle ComplianceChecklist en DB."""

    def test_create_checklist_item(self, db_session):
        from app.models import User, ComplianceChecklist
        from app.auth import hash_password

        user = User(email="comp-test@example.com", password_hash=hash_password("test"), plan="starter")
        db_session.add(user)
        db_session.commit()

        item = ComplianceChecklist(
            user_id=user.id,
            domain="example.com",
            item_id="org_incident_plan",
            checked=True,
            notes="Done in Q1",
        )
        db_session.add(item)
        db_session.commit()
        db_session.refresh(item)

        assert item.id is not None
        assert item.checked is True
        assert item.notes == "Done in Q1"
        assert item.domain == "example.com"
        assert item.item_id == "org_incident_plan"

    def test_unique_constraint(self, db_session):
        """user_id + domain + item_id doit être unique."""
        from app.models import User, ComplianceChecklist
        from app.auth import hash_password
        from sqlalchemy.exc import IntegrityError

        user = User(email="comp-uniq@example.com", password_hash=hash_password("test"), plan="starter")
        db_session.add(user)
        db_session.commit()

        i1 = ComplianceChecklist(user_id=user.id, domain="a.com", item_id="org_mfa", checked=False)
        db_session.add(i1)
        db_session.commit()

        i2 = ComplianceChecklist(user_id=user.id, domain="a.com", item_id="org_mfa", checked=True)
        db_session.add(i2)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_different_domains_allowed(self, db_session):
        """Même user + même item_id mais domaines différents → OK."""
        from app.models import User, ComplianceChecklist
        from app.auth import hash_password

        user = User(email="comp-multi@example.com", password_hash=hash_password("test"), plan="starter")
        db_session.add(user)
        db_session.commit()

        i1 = ComplianceChecklist(user_id=user.id, domain="a.com", item_id="org_mfa", checked=True)
        i2 = ComplianceChecklist(user_id=user.id, domain="b.com", item_id="org_mfa", checked=False)
        db_session.add_all([i1, i2])
        db_session.commit()

        items = db_session.query(ComplianceChecklist).filter_by(user_id=user.id).all()
        assert len(items) == 2

    def test_user_relationship(self, db_session):
        from app.models import User, ComplianceChecklist
        from app.auth import hash_password

        user = User(email="comp-rel@example.com", password_hash=hash_password("test"), plan="starter")
        db_session.add(user)
        db_session.commit()

        item = ComplianceChecklist(user_id=user.id, domain="x.com", item_id="org_backup", checked=False)
        db_session.add(item)
        db_session.commit()
        db_session.refresh(item)

        assert item.user.email == "comp-rel@example.com"

    def test_defaults(self, db_session):
        from app.models import User, ComplianceChecklist
        from app.auth import hash_password

        user = User(email="comp-defaults@example.com", password_hash=hash_password("test"), plan="free")
        db_session.add(user)
        db_session.commit()

        item = ComplianceChecklist(user_id=user.id, domain="d.com", item_id="org_bcp")
        db_session.add(item)
        db_session.commit()
        db_session.refresh(item)

        assert item.checked is False
        assert item.notes is None
        assert item.created_at is not None
