"""
SQLAlchemy Models — User, ScanHistory, ScanRateLimit
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Float, Text,
    DateTime, Boolean, ForeignKey, Index
)
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    email         = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    plan          = Column(String(20), default="free", nullable=False)  # free | pro | team
    is_active     = Column(Boolean, default=True)
    is_admin      = Column(Boolean, default=False)   # True uniquement pour les vrais admins WEZEA
    mfa_enabled   = Column(Boolean, default=False)
    mfa_secret    = Column(String(64), nullable=True)
    api_key       = Column(String(64), unique=True, nullable=True, index=True)
    # ── Profil RGPD ────────────────────────────────────────────────────────────
    first_name    = Column(String(100), nullable=True)
    last_name     = Column(String(100), nullable=True)
    # ── OAuth ──────────────────────────────────────────────────────────────────
    google_id     = Column(String(128), nullable=True, unique=True)
    # ── White-branding (Pro) ───────────────────────────────────────────────────
    wb_enabled       = Column(Boolean,     default=False, nullable=False)
    wb_company_name  = Column(String(100), nullable=True)
    wb_logo_b64      = Column(Text,        nullable=True)   # base64 encoded logo (PNG/JPG/SVG ≤ 200 Ko)
    wb_primary_color = Column(String(7),   nullable=True)   # hex ex. "#3B82F6"
    # ── Abonnement ─────────────────────────────────────────────────────────────
    subscription_status     = Column(String(20), nullable=True)          # active | cancelled | expired
    subscription_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at    = Column(DateTime(timezone=True), default=utcnow)
    updated_at    = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    scans    = relationship("ScanHistory", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment",     back_populates="user", cascade="all, delete-orphan")

    @property
    def scan_limit_per_day(self) -> int | None:
        """None = unlimited."""
        limits = {"free": 5, "starter": None, "pro": None, "team": None}
        return limits.get(self.plan, 5)


class ScanHistory(Base):
    __tablename__ = "scan_history"

    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    scan_uuid      = Column(String(36), unique=True, index=True, nullable=False)
    domain         = Column(String(253), nullable=False, index=True)
    security_score = Column(Integer, nullable=False)
    risk_level     = Column(String(20), nullable=False)
    findings_count = Column(Integer, default=0)
    findings_json  = Column(Text, nullable=True)   # full JSON blob
    scan_duration  = Column(Float, nullable=True)  # ms
    created_at     = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="scans")

    def get_findings(self) -> list:
        if self.findings_json:
            return json.loads(self.findings_json)
        return []


class Payment(Base):
    """Historique des paiements Stripe."""
    __tablename__ = "payments"

    id                 = Column(Integer, primary_key=True, index=True)
    user_id            = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    stripe_session_id  = Column(String(128), unique=True, nullable=False, index=True)
    amount             = Column(Integer, nullable=False)          # en centimes
    currency           = Column(String(3), default="EUR")
    status             = Column(String(20), default="pending")   # pending | completed | cancelled | failed
    created_at         = Column(DateTime(timezone=True), default=utcnow)
    paid_at            = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="payments")


class MonitoredDomain(Base):
    """Domaines sous surveillance automatique (Starter / Pro)."""
    __tablename__ = "monitored_domains"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    domain          = Column(String(253), nullable=False, index=True)
    last_score           = Column(Integer, nullable=True)
    last_risk_level      = Column(String(20), nullable=True)
    last_scan_at         = Column(DateTime(timezone=True), nullable=True)
    alert_threshold      = Column(Integer, default=10)   # alerte si score baisse de X points
    is_active            = Column(Boolean, default=True)
    checks_config        = Column(Text, nullable=True)   # JSON: {"dns":true,"ssl":true,"ports":true,...}
    created_at           = Column(DateTime(timezone=True), default=utcnow)
    # ── Surveillance élargie ─────────────────────────────────────────────
    last_ssl_expiry_days = Column(Integer, nullable=True)  # jours restants sur le cert SSL
    last_open_ports      = Column(Text, nullable=True)     # JSON: ["80","443","22"]
    last_technologies    = Column(Text, nullable=True)     # JSON: {"nginx":"1.24.0"}
    # ── Scan programmé ───────────────────────────────────────────────────
    scan_frequency       = Column(String(20), default="weekly")  # weekly|biweekly|monthly
    email_report         = Column(Boolean, default=False)        # envoyer PDF par email

    user = relationship("User", backref="monitored_domains")

    # Checks activés par défaut
    DEFAULT_CHECKS: dict = {
        "dns":        True,
        "ssl":        True,
        "ports":      True,
        "headers":    True,
        "email":      True,
        "tech":       True,
        "reputation": True,
    }

    def get_checks_config(self) -> dict:
        """Retourne la config des checks, en fusionnant avec les défauts."""
        if self.checks_config:
            stored = json.loads(self.checks_config)
            return {**self.DEFAULT_CHECKS, **stored}
        return dict(self.DEFAULT_CHECKS)

    __table_args__ = (
        Index("ix_user_domain", "user_id", "domain", unique=True),
    )


class ScanRateLimit(Base):
    """Tracks anonymous scan usage per client (cookie or IP) per day."""
    __tablename__ = "scan_rate_limits"

    id         = Column(Integer, primary_key=True, index=True)
    client_id  = Column(String(64), nullable=False)  # cookie wezea_cid, "ip:<addr>" pour le verrou IP secondaire
    date_key   = Column(String(10), nullable=False)  # e.g. "2026-03-04" (YYYY-MM-DD)
    scan_count = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_client_day", "client_id", "date_key", unique=True),
    )


class ContactMessage(Base):
    """Stocke les demandes de support des utilisateurs."""
    __tablename__ = "contact_messages"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(120), nullable=False)
    email      = Column(String(120), nullable=False)
    subject    = Column(String(200), nullable=False)
    message    = Column(Text, nullable=False)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=True)  # si connecté
    created_at = Column(DateTime(timezone=True), default=utcnow, index=True)


class NewsletterSubscription(Base):
    """Abonnements newsletter — double opt-in RGPD."""
    __tablename__ = "newsletter_subscriptions"

    id           = Column(Integer, primary_key=True, index=True)
    email        = Column(String(254), nullable=False, unique=True, index=True)
    token        = Column(String(64), nullable=True, unique=True, index=True)   # token de confirmation
    confirmed    = Column(Boolean, default=False, nullable=False)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    unsubscribed = Column(Boolean, default=False, nullable=False)
    created_at   = Column(DateTime(timezone=True), default=utcnow, index=True)
    ip_address   = Column(String(45), nullable=True)   # IPv4/IPv6, pour preuve RGPD
