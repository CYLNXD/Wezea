"""
CyberHealth Scanner — Scheduler de monitoring
==============================================
Utilise APScheduler (BackgroundScheduler) avec un verrou fichier
pour garantir qu'un seul worker gunicorn exécute les scans.

Planification : chaque lundi à 06:00 UTC

Features :
  - Feature 2 : Surveillance élargie — SSL expiry, ports ouverts, versions techno
  - Feature 3 : Fréquence de scan par domaine (weekly/biweekly/monthly)
                + envoi PDF par email si email_report=True
"""
from __future__ import annotations

import asyncio
import fcntl
import json as _json
import logging
import os
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger("cyberhealth.scheduler")

LOCK_FILE = "/tmp/cyberhealth_scheduler.lock"
_lock_fd = None
_scheduler: BackgroundScheduler | None = None


def _try_acquire_lock() -> bool:
    """Tente d'acquérir un verrou exclusif — retourne False si un autre worker le détient."""
    global _lock_fd
    try:
        _lock_fd = open(LOCK_FILE, "w")
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except IOError:
        return False


def _release_lock() -> None:
    global _lock_fd
    if _lock_fd:
        try:
            fcntl.flock(_lock_fd, fcntl.LOCK_UN)
            _lock_fd.close()
        except Exception:
            pass
        _lock_fd = None


# ─────────────────────────────────────────────────────────────────────────────
# Feature 3 : Fréquence de scan par domaine
# ─────────────────────────────────────────────────────────────────────────────

def _should_scan_now(monitored: "MonitoredDomain") -> bool:
    """
    Retourne True si le domaine doit être scanné maintenant selon sa fréquence.
    weekly    → 6+ jours depuis le dernier scan
    biweekly  → 13+ jours
    monthly   → 28+ jours
    """
    if monitored.last_scan_at is None:
        return True  # Jamais scanné — toujours scanner

    freq    = monitored.scan_frequency or "weekly"
    now     = datetime.now(timezone.utc)
    elapsed = now - monitored.last_scan_at

    if freq == "biweekly":
        return elapsed.days >= 13
    elif freq == "monthly":
        return elapsed.days >= 28
    else:  # weekly (défaut)
        return elapsed.days >= 6


# ─────────────────────────────────────────────────────────────────────────────
# Tâche principale : scanner tous les domaines surveillés
# ─────────────────────────────────────────────────────────────────────────────

def run_weekly_monitoring():
    """Point d'entrée appelé par APScheduler chaque lundi à 06:00 UTC."""
    logger.info("🔍 Démarrage du monitoring hebdomadaire...")
    try:
        asyncio.run(_async_monitoring())
    except Exception as e:
        logger.error(f"Erreur monitoring hebdomadaire : {e}")


async def _async_monitoring():
    from app.database import SessionLocal
    from app.models import MonitoredDomain, User
    from app.scanner import AuditManager

    db = SessionLocal()
    try:
        domains = (
            db.query(MonitoredDomain)
            .filter(MonitoredDomain.is_active == True)
            .all()
        )
        logger.info(f"Monitoring : {len(domains)} domaine(s) actif(s)")

        for monitored in domains:
            # Feature 3 : Vérifier si le scan est dû selon la fréquence configurée
            if not _should_scan_now(monitored):
                logger.info(
                    f"Monitoring : {monitored.domain} — skip "
                    f"(fréquence={monitored.scan_frequency}, "
                    f"dernier scan={monitored.last_scan_at})"
                )
                continue

            try:
                await _scan_and_alert(monitored, db)
            except Exception as e:
                logger.error(f"Erreur scan monitoring {monitored.domain} : {e}")
    finally:
        db.close()


async def _scan_and_alert(monitored: "MonitoredDomain", db) -> None:
    from app.scanner import AuditManager
    from app.models import User

    user = db.query(User).filter(User.id == monitored.user_id).first()
    if not user or not user.is_active:
        return

    plan       = user.plan if user.plan in ("starter", "pro") else "starter"
    checks_cfg = monitored.get_checks_config()

    logger.info(f"Scan monitoring : {monitored.domain} (user {user.email}, plan {plan})")

    manager = AuditManager(monitored.domain, lang="fr", plan=plan, checks_config=checks_cfg)
    result  = await manager.run()

    new_score  = result.security_score
    new_risk   = result.risk_level
    prev_score = monitored.last_score
    threshold  = monitored.alert_threshold

    # ── Alertes configurables ─────────────────────────────────────────────────
    alert_cfg     = monitored.get_alert_config()
    ssl_threshold = monitored.ssl_alert_days or 30

    # ── Feature 2 : Surveillance élargie — SSL, ports, technologies ──────────
    change_alerts: list[str] = []

    # 1. SSL expiry (seuil configurable)
    new_ssl_days: int | None = result.ssl_details.get("days_left")
    if new_ssl_days is not None:
        if alert_cfg["ssl_expiry"]:
            if new_ssl_days <= 7:
                change_alerts.append(
                    f"🚨 Certificat SSL expire dans {new_ssl_days} jour(s) — renouvellement urgent !"
                )
            elif new_ssl_days <= ssl_threshold:
                change_alerts.append(
                    f"⚠️ Certificat SSL expire dans {new_ssl_days} jours (seuil configuré : {ssl_threshold}j)"
                )
        monitored.last_ssl_expiry_days = new_ssl_days

    # 2. Open ports — détecter nouveaux ports ouverts / ports fermés
    new_open_ports: list[str] = [
        str(p) for p, v in result.port_details.items() if v.get("open")
    ]
    prev_ports_raw   = monitored.last_open_ports
    prev_open_ports: list[str] = _json.loads(prev_ports_raw) if prev_ports_raw else []

    new_ports_set  = set(new_open_ports)
    prev_ports_set = set(prev_open_ports)
    newly_opened   = new_ports_set - prev_ports_set
    newly_closed   = prev_ports_set - new_ports_set

    if alert_cfg["port_changes"]:
        if newly_opened:
            change_alerts.append(
                f"🔓 Nouveaux ports ouverts : {', '.join(sorted(newly_opened))}"
            )
        if newly_closed:
            change_alerts.append(
                f"🔒 Ports fermés : {', '.join(sorted(newly_closed))}"
            )
    monitored.last_open_ports = _json.dumps(new_open_ports)

    # 3. Technologies — détecter changements de versions
    new_stack    = result.vuln_details.get("detected_stack", [])
    new_tech_map: dict[str, str] = {
        item["tech"]: item.get("version", "") for item in new_stack
    }
    prev_tech_raw  = monitored.last_technologies
    prev_tech_map: dict[str, str] = _json.loads(prev_tech_raw) if prev_tech_raw else {}

    tech_changes: list[str] = []
    for tech, new_ver in new_tech_map.items():
        if tech in prev_tech_map and prev_tech_map[tech] != new_ver and new_ver:
            tech_changes.append(f"{tech}: {prev_tech_map[tech]} → {new_ver}")

    if alert_cfg["tech_changes"] and tech_changes:
        change_alerts.append(
            f"🔄 Changements de versions : {'; '.join(tech_changes[:3])}"
        )
    monitored.last_technologies = _json.dumps(new_tech_map)
    # ── fin Feature 2 ─────────────────────────────────────────────────────────

    # Mettre à jour en DB
    monitored.last_score      = new_score
    monitored.last_risk_level = new_risk
    monitored.last_scan_at    = datetime.now(timezone.utc)
    db.commit()

    # Décider si on envoie une alerte
    should_alert = False
    alert_reason = ""

    if alert_cfg["score_drop"] and prev_score is not None:
        drop = prev_score - new_score
        if drop >= threshold:
            should_alert  = True
            alert_reason  = f"Score en baisse de {drop} points ({prev_score} → {new_score})"

    # Nouveau finding CRITICAL ?
    critical_findings = [
        f for f in result.findings
        if f.severity == "CRITICAL" and f.penalty > 0
    ]
    if alert_cfg["critical_findings"] and critical_findings:
        should_alert = True
        if alert_reason:
            alert_reason += f" + {len(critical_findings)} finding(s) critique(s)"
        else:
            alert_reason = f"{len(critical_findings)} nouveau(x) finding(s) critique(s) détecté(s)"

    # Feature 2 : Intégrer les alertes de changements élargie
    if change_alerts:
        should_alert = True
        changes_str  = " | ".join(change_alerts)
        alert_reason = f"{alert_reason} | {changes_str}" if alert_reason else changes_str

    if should_alert:
        logger.info(f"Alerte monitoring pour {monitored.domain} : {alert_reason}")
        await _send_monitoring_alert(
            email       = user.email,
            first_name  = user.first_name or user.email.split("@")[0],
            domain      = monitored.domain,
            new_score   = new_score,
            prev_score  = prev_score,
            risk_level  = new_risk,
            reason      = alert_reason,
            findings    = critical_findings[:3],
        )
        # Webhooks : alert.triggered
        try:
            from app.routers.webhook_router import fire_webhooks
            await fire_webhooks(
                user_id = user.id,
                event   = "alert.triggered",
                payload = {"data": {
                    "domain":     monitored.domain,
                    "new_score":  new_score,
                    "prev_score": prev_score,
                    "risk_level": new_risk,
                    "reason":     alert_reason,
                }},
                db = db,
            )
        except Exception as _wh_err:
            logger.error(f"Webhook alert.triggered {monitored.domain}: {_wh_err}")

        # Intégrations Slack / Teams
        _reasons = [r.strip() for r in alert_reason.split("|") if r.strip()] if alert_reason else []
        if user.slack_webhook_url:
            try:
                from app.services.brevo_service import send_slack_alert
                await send_slack_alert(
                    webhook_url = user.slack_webhook_url,
                    domain      = monitored.domain,
                    score       = new_score,
                    risk_level  = new_risk,
                    reasons     = _reasons,
                )
            except Exception as _sl_err:
                logger.error(f"Slack alert {monitored.domain}: {_sl_err}")
        if user.teams_webhook_url:
            try:
                from app.services.brevo_service import send_teams_alert
                await send_teams_alert(
                    webhook_url = user.teams_webhook_url,
                    domain      = monitored.domain,
                    score       = new_score,
                    risk_level  = new_risk,
                    reasons     = _reasons,
                )
            except Exception as _tm_err:
                logger.error(f"Teams alert {monitored.domain}: {_tm_err}")
    else:
        logger.info(f"Monitoring OK : {monitored.domain} — score {new_score} (stable)")

    # Webhooks : score.dropped (indépendant de should_alert)
    if prev_score is not None and (prev_score - new_score) >= monitored.alert_threshold:
        try:
            from app.routers.webhook_router import fire_webhooks
            await fire_webhooks(
                user_id = user.id,
                event   = "score.dropped",
                payload = {"data": {
                    "domain":     monitored.domain,
                    "new_score":  new_score,
                    "prev_score": prev_score,
                    "drop":       prev_score - new_score,
                }},
                db = db,
            )
        except Exception as _wh_err:
            logger.error(f"Webhook score.dropped {monitored.domain}: {_wh_err}")

    # ── Feature 3 : Envoi du rapport PDF programmé ────────────────────────────
    if monitored.email_report:
        try:
            await _send_scheduled_pdf_report(
                user      = user,
                monitored = monitored,
                result    = result,
            )
        except Exception as e:
            logger.error(f"Erreur envoi PDF programmé {monitored.domain} : {e}")
    # ── fin Feature 3 ─────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# Feature 3 : Génération et envoi du rapport PDF programmé
# ─────────────────────────────────────────────────────────────────────────────

async def _send_scheduled_pdf_report(user, monitored, result) -> None:
    """Génère le rapport PDF et l'envoie par email (Feature 3)."""
    from app.services import report_service
    from app.services.brevo_service import send_pdf_email

    try:
        audit_data = result.to_dict()
        loop       = asyncio.get_event_loop()
        pdf_bytes  = await loop.run_in_executor(
            None,
            lambda: report_service.generate_pdf(audit_data, "fr"),
        )
        await send_pdf_email(
            email      = user.email,
            domain     = monitored.domain,
            pdf_bytes  = pdf_bytes,
            score      = result.security_score,
            risk_level = result.risk_level,
        )
        logger.info(f"📧 Rapport PDF programmé envoyé à {user.email} pour {monitored.domain}")
    except Exception as e:
        logger.error(f"Erreur génération/envoi PDF {monitored.domain} : {e}")
        raise


async def _send_monitoring_alert(
    email: str,
    first_name: str,
    domain: str,
    new_score: int,
    prev_score: int | None,
    risk_level: str,
    reason: str,
    findings: list,
) -> None:
    """Envoie un email d'alerte de monitoring via Brevo."""
    from app.services.brevo_service import send_monitoring_alert_email
    await send_monitoring_alert_email(
        email      = email,
        first_name = first_name,
        domain     = domain,
        new_score  = new_score,
        prev_score = prev_score,
        risk_level = risk_level,
        reason     = reason,
        findings   = findings,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Emails d'onboarding : séquence complète J+1 / J+3 / J+7 / J+14
# ─────────────────────────────────────────────────────────────────────────────

def run_daily_onboarding_emails():
    """
    Tâche quotidienne (09:00 UTC) — envoie quatre types de relances :
    - J+1  : utilisateurs sans aucun scan → nudge "faites votre premier scan"
    - J+3  : utilisateurs free sans upgrade → nudge "passez à Starter"
    - J+7  : utilisateurs free ayant scanné → rappel valeur + upsell monitoring
    - J+14 : utilisateurs free toujours là → dernière relance win-back

    La fenêtre de détection (±4h autour de chaque jour) garantit
    qu'un email est envoyé une seule fois par utilisateur même si
    le job a quelques minutes de décalage.
    """
    logger.info("📧 Démarrage des emails d'onboarding quotidiens...")
    try:
        asyncio.run(_async_onboarding_emails())
    except Exception as e:
        logger.error(f"Erreur emails onboarding : {e}")


async def _async_onboarding_emails():
    from app.database import SessionLocal
    from app.models import User, ScanHistory
    from app.services.brevo_service import (
        send_activation_nudge_email,
        send_upgrade_nudge_email,
        send_value_reminder_email,
        send_winback_email,
    )

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        # ── J+1 : inscrits il y a 20–28h, zéro scan ─────────────────────────
        window_j1_start = now - timedelta(hours=28)
        window_j1_end   = now - timedelta(hours=20)

        users_j1 = (
            db.query(User)
            .filter(
                User.is_active == True,
                User.created_at >= window_j1_start,
                User.created_at <= window_j1_end,
                User.plan == "free",
            )
            .all()
        )

        for user in users_j1:
            scan_count = (
                db.query(ScanHistory)
                .filter(ScanHistory.user_id == user.id)
                .count()
            )
            if scan_count == 0:
                logger.info(f"Onboarding J+1 : {user.email} (0 scans)")
                try:
                    await send_activation_nudge_email(user.email)
                except Exception as e:
                    logger.error(f"Erreur nudge J+1 {user.email} : {e}")
            else:
                logger.debug(f"Onboarding J+1 skip : {user.email} ({scan_count} scan(s))")

        # ── J+3 : inscrits il y a 68–76h, toujours free ──────────────────────
        window_j3_start = now - timedelta(hours=76)
        window_j3_end   = now - timedelta(hours=68)

        users_j3 = (
            db.query(User)
            .filter(
                User.is_active == True,
                User.created_at >= window_j3_start,
                User.created_at <= window_j3_end,
                User.plan == "free",
            )
            .all()
        )

        for user in users_j3:
            logger.info(f"Onboarding J+3 upgrade nudge : {user.email}")
            try:
                await send_upgrade_nudge_email(user.email)
            except Exception as e:
                logger.error(f"Erreur nudge J+3 {user.email} : {e}")

        # ── J+7 : inscrits il y a 164–172h, free, au moins 1 scan ───────────
        window_j7_start = now - timedelta(hours=172)
        window_j7_end   = now - timedelta(hours=164)

        users_j7 = (
            db.query(User)
            .filter(
                User.is_active == True,
                User.created_at >= window_j7_start,
                User.created_at <= window_j7_end,
                User.plan == "free",
            )
            .all()
        )

        for user in users_j7:
            scan_count = (
                db.query(ScanHistory)
                .filter(ScanHistory.user_id == user.id)
                .count()
            )
            if scan_count >= 1:
                logger.info(f"Onboarding J+7 value reminder : {user.email} ({scan_count} scan(s))")
                try:
                    await send_value_reminder_email(user.email, scan_count)
                except Exception as e:
                    logger.error(f"Erreur value reminder J+7 {user.email} : {e}")
            else:
                logger.debug(f"Onboarding J+7 skip : {user.email} (0 scan)")

        # ── J+14 : inscrits il y a 332–340h, toujours free ───────────────────
        window_j14_start = now - timedelta(hours=340)
        window_j14_end   = now - timedelta(hours=332)

        users_j14 = (
            db.query(User)
            .filter(
                User.is_active == True,
                User.created_at >= window_j14_start,
                User.created_at <= window_j14_end,
                User.plan == "free",
            )
            .all()
        )

        for user in users_j14:
            logger.info(f"Onboarding J+14 win-back : {user.email}")
            try:
                await send_winback_email(user.email)
            except Exception as e:
                logger.error(f"Erreur win-back J+14 {user.email} : {e}")

        logger.info(
            f"Onboarding terminé — {len(users_j1)} J+1, {len(users_j3)} J+3, "
            f"{len(users_j7)} J+7, {len(users_j14)} J+14"
        )

    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Résumé hebdomadaire : digest lundi 07:30 UTC
# ─────────────────────────────────────────────────────────────────────────────

def run_weekly_digest():
    """Point d'entrée APScheduler — lundi 07:30 UTC."""
    logger.info("📊 Démarrage du digest hebdomadaire de monitoring...")
    try:
        asyncio.run(_async_weekly_digest())
    except Exception as e:
        logger.error(f"Erreur digest hebdomadaire : {e}")


async def _async_weekly_digest():
    from app.database import SessionLocal
    from app.models import MonitoredDomain, User
    from app.services.brevo_service import send_weekly_monitoring_digest

    db = SessionLocal()
    try:
        # Récupérer tous les users ayant au moins un domaine actif
        active_users = (
            db.query(User)
            .join(MonitoredDomain, MonitoredDomain.user_id == User.id)
            .filter(
                MonitoredDomain.is_active == True,
                User.is_active == True,
            )
            .distinct()
            .all()
        )
        logger.info(f"Digest hebdomadaire : {len(active_users)} utilisateur(s) avec domaines actifs")

        for user in active_users:
            try:
                domains = (
                    db.query(MonitoredDomain)
                    .filter(
                        MonitoredDomain.user_id == user.id,
                        MonitoredDomain.is_active == True,
                    )
                    .all()
                )
                if not domains:
                    continue

                domain_data = []
                for d in domains:
                    domain_data.append({
                        "domain":          d.domain,
                        "score":           d.last_score,
                        "risk_level":      d.last_risk_level or "UNKNOWN",
                        "ssl_expiry_days": d.last_ssl_expiry_days,
                        "last_scan_at":    (
                            d.last_scan_at.strftime("%d/%m/%Y")
                            if d.last_scan_at else "Jamais"
                        ),
                        "open_ports":      (
                            _json.loads(d.last_open_ports)
                            if d.last_open_ports else []
                        ),
                    })

                await send_weekly_monitoring_digest(
                    email      = user.email,
                    first_name = user.first_name or user.email.split("@")[0],
                    domains    = domain_data,
                )
                logger.info(f"Digest envoyé à {user.email} ({len(domain_data)} domaine(s))")
            except Exception as e:
                logger.error(f"Erreur digest pour {user.email} : {e}")

    except Exception as e:
        logger.error(f"[digest] Erreur globale : {e}")
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Démarrage / arrêt du scheduler
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Purge automatique des scans anciens (RGPD — rétention 90 jours)
# ─────────────────────────────────────────────────────────────────────────────

PURGE_RETENTION_DAYS = 90


def purge_old_scans(retention_days: int = PURGE_RETENTION_DAYS) -> int:
    """
    Supprime les scans dont created_at < now - retention_days.
    Retourne le nombre de lignes supprimées.
    Conçu pour être appelé par APScheduler (synchrone) et par l'endpoint admin.
    """
    from datetime import timedelta
    from sqlalchemy import delete
    from app.database import SessionLocal
    from app.models import ScanHistory

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted = 0
    db = SessionLocal()
    try:
        result = db.execute(
            delete(ScanHistory).where(ScanHistory.created_at < cutoff)
        )
        db.commit()
        deleted = result.rowcount
        logger.info(f"🧹 Purge scans : {deleted} enregistrement(s) supprimé(s) (rétention {retention_days}j)")
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur purge scans : {e}")
    finally:
        db.close()
    return deleted


def start_scheduler() -> bool:
    """
    Démarre le scheduler si ce worker obtient le verrou.
    Retourne True si le scheduler a démarré, False sinon.
    """
    global _scheduler

    if not _try_acquire_lock():
        logger.info("Scheduler : verrou déjà détenu par un autre worker — skipping")
        return False

    _scheduler = BackgroundScheduler(timezone="UTC")

    # Chaque lundi à 06:00 UTC — monitoring des domaines surveillés
    _scheduler.add_job(
        run_weekly_monitoring,
        trigger="cron",
        day_of_week="mon",
        hour=6,
        minute=0,
        id="weekly_monitoring",
        replace_existing=True,
        misfire_grace_time=3600,  # 1h de tolérance si le serveur était down
    )

    # Chaque jour à 09:00 UTC — emails d'onboarding (nudge J+1 et J+3)
    _scheduler.add_job(
        run_daily_onboarding_emails,
        trigger="cron",
        hour=9,
        minute=0,
        id="daily_onboarding",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Chaque lundi à 07:30 UTC — digest récapitulatif de surveillance
    _scheduler.add_job(
        run_weekly_digest,
        trigger="cron",
        day_of_week="mon",
        hour=7,
        minute=30,
        id="weekly_digest",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Chaque jour à 03:00 UTC — purge RGPD des scans > 90 jours
    _scheduler.add_job(
        purge_old_scans,
        trigger="cron",
        hour=3,
        minute=0,
        id="daily_purge",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.start()
    logger.info(
        "✅ Scheduler démarré — monitoring hebdomadaire lundi 06:00 UTC"
        " | digest lundi 07:30 UTC"
        " | onboarding quotidien 09:00 UTC"
        " | purge RGPD quotidienne 03:00 UTC"
    )
    return True


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler arrêté.")
    _release_lock()
