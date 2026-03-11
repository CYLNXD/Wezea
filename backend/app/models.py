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
    api_key       = Column(String(64), unique=True, nullable=True, index=True)   # DEPRECATED → migration 014 → api_key_hash
    api_key_hash  = Column(String(64), unique=True, nullable=True, index=True)   # HMAC-SHA256(key, SECRET_KEY)
    api_key_hint  = Column(String(24), nullable=True)                            # wsk_AbCdEfGh...wxyz (affichage)
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
    stripe_customer_id      = Column(String(64), nullable=True, index=True)  # cus_xxx — lien permanent Stripe
    subscription_status     = Column(String(20), nullable=True)          # active | cancelled | expired
    subscription_expires_at = Column(DateTime(timezone=True), nullable=True)
    # ── Réinitialisation du mot de passe ───────────────────────────────────────
    password_reset_token    = Column(String(64), nullable=True, index=True)
    password_reset_expires  = Column(DateTime(timezone=True), nullable=True)
    # ── Intégrations (Slack / Teams) ───────────────────────────────────────────
    slack_webhook_url  = Column(String(512), nullable=True)   # https://hooks.slack.com/...
    teams_webhook_url  = Column(String(512), nullable=True)   # https://...webhook.office.com/...
    created_at    = Column(DateTime(timezone=True), default=utcnow)
    updated_at    = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    scans    = relationship("ScanHistory", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment",     back_populates="user", cascade="all, delete-orphan")

    @property
    def scan_limit_per_day(self) -> int | None:
        """None = unlimited."""
        limits = {"free": 5, "starter": None, "pro": None, "dev": None}
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
    scan_details_json = Column(Text, nullable=True) # dns_details, ssl_details, port_details, recommendations, subdomain_details, vuln_details
    scan_duration  = Column(Float, nullable=True)  # ms
    public_share   = Column(Boolean, default=False, nullable=False)  # lien public /r/{uuid}
    created_at     = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="scans")

    def get_findings(self) -> list:
        if self.findings_json:
            return json.loads(self.findings_json)
        return []

    def get_scan_details(self) -> dict:
        if self.scan_details_json:
            return json.loads(self.scan_details_json)
        return {}


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
    # ── Alertes configurables ─────────────────────────────────────────────
    ssl_alert_days       = Column(Integer, default=30)           # seuil SSL (jours) avant alerte
    alert_config         = Column(Text, nullable=True)           # JSON: {"score_drop":bool,...}

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

    DEFAULT_ALERT_CONFIG: dict = {
        "score_drop":         True,
        "critical_findings":  True,
        "ssl_expiry":         True,
        "port_changes":       True,
        "tech_changes":       True,
    }

    def get_checks_config(self) -> dict:
        """Retourne la config des checks, en fusionnant avec les défauts.
        Seules les clés connues (DEFAULT_CHECKS) sont conservées."""
        if self.checks_config:
            try:
                stored = json.loads(self.checks_config)
            except (json.JSONDecodeError, TypeError):
                return dict(self.DEFAULT_CHECKS)
            # Ne garder que les clés connues avec valeurs booléennes
            sanitized = {
                k: bool(v)
                for k, v in stored.items()
                if k in self.DEFAULT_CHECKS
            }
            return {**self.DEFAULT_CHECKS, **sanitized}
        return dict(self.DEFAULT_CHECKS)

    def get_alert_config(self) -> dict:
        """Retourne la config d'alertes avec fallback aux defaults."""
        if not self.alert_config:
            return dict(self.DEFAULT_ALERT_CONFIG)
        try:
            return {**self.DEFAULT_ALERT_CONFIG, **json.loads(self.alert_config)}
        except Exception:
            return dict(self.DEFAULT_ALERT_CONFIG)

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


class LoginAttempt(Base):
    """
    Compteur d'échecs de connexion par IP — remplace le dict in-memory _login_failures.
    Partagé entre tous les workers gunicorn/uvicorn (persisté en DB).
    Nettoyage automatique lors de la vérification (fenêtre glissante 15 min).
    """
    __tablename__ = "login_attempts"

    id         = Column(Integer, primary_key=True, index=True)
    ip         = Column(String(45), nullable=False, index=True)  # IPv4 ou IPv6
    failed_at  = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_login_attempts_ip_time", "ip", "failed_at"),
    )


class VerifiedApp(Base):
    """
    Applications web enregistrées pour l'Application Scanning.
    L'ownership est vérifiée par DNS TXT ou fichier .well-known.
    Réservé aux plans Starter et Pro.
    """
    __tablename__ = "verified_apps"

    id                   = Column(Integer, primary_key=True, index=True)
    user_id              = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name                 = Column(String(100), nullable=False)            # Nom affiché
    url                  = Column(String(512), nullable=False)            # URL de base (ex: https://myapp.example.com)
    domain               = Column(String(253), nullable=False)            # Host extrait de l'URL
    # ── Vérification d'ownership ───────────────────────────────────────────
    verification_method  = Column(String(10), nullable=False, default="dns")  # "dns" | "file"
    verification_token   = Column(String(64), nullable=False)             # Token unique généré
    is_verified          = Column(Boolean, default=False)
    verified_at          = Column(DateTime(timezone=True), nullable=True)
    # ── Dernier scan ──────────────────────────────────────────────────────
    last_scan_at         = Column(DateTime(timezone=True), nullable=True)
    last_score           = Column(Integer, nullable=True)
    last_risk_level      = Column(String(20), nullable=True)
    last_findings_json   = Column(Text, nullable=True)    # JSON findings
    last_details_json    = Column(Text, nullable=True)    # JSON details
    created_at           = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", backref="verified_apps")

    __table_args__ = (
        Index("ix_user_app_url", "user_id", "url", unique=True),
    )

    def get_last_findings(self) -> list:
        if self.last_findings_json:
            return json.loads(self.last_findings_json)
        return []

    def get_last_details(self) -> dict:
        if self.last_details_json:
            return json.loads(self.last_details_json)
        return {}


class BlogLink(Base):
    """
    Liens articles de blog associés à des mots-clés de recommandations.
    Géré par l'admin — affiché dans l'onglet Recommandations du Dashboard.
    Le matching est fait côté frontend (contains insensible à la casse).
    """
    __tablename__ = "blog_links"

    id            = Column(Integer, primary_key=True, index=True)
    match_keyword = Column(String(100), nullable=False, index=True)  # ex: "SPF", "HSTS", "RDP"
    article_title = Column(String(200), nullable=False)
    article_url   = Column(String(500), nullable=False)
    created_at    = Column(DateTime(timezone=True), default=utcnow)


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


class Webhook(Base):
    """Webhooks sortants — appelés après scan/alerte (plan Pro uniquement)."""
    __tablename__ = "webhooks"

    id            = Column(Integer, primary_key=True, index=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    url           = Column(String(512), nullable=False)
    secret        = Column(String(64), nullable=True)   # secret HMAC-SHA256 pour la signature
    events        = Column(Text, nullable=True)         # JSON: ["scan.completed", "alert.triggered"]
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime(timezone=True), default=utcnow)
    last_fired_at = Column(DateTime(timezone=True), nullable=True)
    last_status   = Column(Integer, nullable=True)      # HTTP status de la dernière livraison

    user = relationship("User", backref="webhooks")
