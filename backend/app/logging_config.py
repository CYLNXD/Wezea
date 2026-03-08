"""
logging_config.py — Configuration des logs JSON structurés
──────────────────────────────────────────────────────────────────────────────
Format de sortie (une ligne JSON par événement) :
  {
    "timestamp": "2026-03-08T21:00:00.000Z",
    "level":     "INFO",
    "logger":    "cyberhealth.main",
    "message":   "GET /scan → 200",
    "method":    "GET",
    "path":      "/scan",
    "status":    200,
    "duration_ms": 142.3,
    "ip":        "1.2.3.4"
  }

Parseable directement par :
  jq  — filtre local
  journald  — avec journalctl -o json
  Datadog / Grafana Loki / ELK — ingestion native JSON

Niveaux configurables via la variable d'environnement LOG_LEVEL (défaut : INFO).
En mode DEBUG (LOG_LEVEL=DEBUG), les requêtes des health checks sont loggées aussi.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Optional

try:
    from pythonjsonlogger import jsonlogger as _jsonlogger
    _JSON_LOGGER_AVAILABLE = True
except ImportError:  # pragma: no cover
    _jsonlogger = None  # type: ignore[assignment]
    _JSON_LOGGER_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Formatter JSON (uniquement si python-json-logger est installé)
# ─────────────────────────────────────────────────────────────────────────────

if _JSON_LOGGER_AVAILABLE:
    class _CyberHealthJsonFormatter(_jsonlogger.JsonFormatter):  # type: ignore[misc]
        """
        Formatter JSON avec :
        - timestamp ISO 8601 UTC  (clé : timestamp)
        - niveau en majuscules    (clé : level)
        - nom du logger           (clé : logger)
        - message                 (clé : message)
        - tous les champs extra   (méthode, path, status, duration_ms, ip…)
        """

        def add_fields(
            self,
            log_record: dict,
            record: logging.LogRecord,
            message_dict: dict,
        ) -> None:
            super().add_fields(log_record, record, message_dict)
            log_record["timestamp"] = log_record.pop("asctime", record.created)
            log_record["level"]     = record.levelname
            log_record["logger"]    = record.name
            log_record.pop("levelname", None)
            log_record.pop("name",      None)


# ─────────────────────────────────────────────────────────────────────────────
# Point d'entrée
# ─────────────────────────────────────────────────────────────────────────────

def setup_logging(log_level: Optional[str] = None) -> None:
    """
    Configure le root logger.
    - Si python-json-logger est installé → format JSON structuré
    - Sinon → format texte classique (fallback, app démarre quand même)
    À appeler UNE SEULE FOIS au démarrage (avant lifespan).
    """
    level_str = (log_level or os.getenv("LOG_LEVEL", "INFO")).upper()
    level     = getattr(logging, level_str, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    if _JSON_LOGGER_AVAILABLE:
        handler.setFormatter(
            _CyberHealthJsonFormatter(
                fmt      = "%(asctime)s %(name)s %(levelname)s %(message)s",
                datefmt  = "%Y-%m-%dT%H:%M:%S",
                json_ensure_ascii = False,
            )
        )
    else:  # pragma: no cover
        # Fallback : format texte lisible — app démarre même sans la lib
        logging.warning(
            "python-json-logger non installé — logs en format texte. "
            "Lancez : pip install python-json-logger==2.0.7"
        )
        handler.setFormatter(logging.Formatter(
            fmt     = "%(asctime)s %(name)s %(levelname)s %(message)s",
            datefmt = "%Y-%m-%dT%H:%M:%S",
        ))

    root = logging.getLogger()
    root.setLevel(level)
    # Remplacer tous les handlers existants (évite les doublons au reload)
    root.handlers = [handler]

    # ── Réduction du bruit des bibliothèques tierces ──────────────────────────
    # uvicorn.access : on gère nous-mêmes le log des requêtes dans le middleware
    logging.getLogger("uvicorn.access").propagate = False
    logging.getLogger("uvicorn.access").handlers  = []

    # SQLAlchemy — seulement les erreurs (évite le flood de requêtes SQL en dev)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

    # APScheduler — INFO suffisant (les jobs se loggent déjà)
    logging.getLogger("apscheduler").setLevel(logging.INFO)

    # httpx / httpcore — WARNING (librairie Brevo, pas d'intérêt en INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Stripe SDK
    logging.getLogger("stripe").setLevel(logging.WARNING)
