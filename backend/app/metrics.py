"""
CyberHealth Scanner — Métriques de performance API
===================================================
Collecte in-memory (deque rolling) des temps de réponse par endpoint.
Zéro écriture en DB — réinitialisé au redémarrage du worker.

Usage :
    from app.metrics import record_request, get_performance_stats
    record_request("/scan", "POST", 200, 142.5)   # ms
    stats = get_performance_stats()
"""
from __future__ import annotations

import statistics
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ─── Configuration ────────────────────────────────────────────────────────────

BUFFER_SIZE   = 2000     # Nombre max d'enregistrements globaux (rolling)
SLOW_THRESHOLD_MS = 500  # Seuil "lent" en millisecondes

# Chemins à ignorer (healthcheck, assets…)
_SKIP_PATHS = {"/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}

# ─── Structures ───────────────────────────────────────────────────────────────

@dataclass
class RequestRecord:
    path:        str
    method:      str
    status_code: int
    duration_ms: float
    ts:          datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# Buffer global thread-safe (accès concurrent depuis plusieurs coroutines)
_lock:   threading.Lock                            = threading.Lock()
_buffer: deque[RequestRecord]                      = deque(maxlen=BUFFER_SIZE)
_counts: dict[str, int]                            = defaultdict(int)   # (method:path) → total hits


# ─── API publique ─────────────────────────────────────────────────────────────

def record_request(
    path: str,
    method: str,
    status_code: int,
    duration_ms: float,
) -> None:
    """Enregistre une requête dans le buffer rolling."""
    if path in _SKIP_PATHS:
        return
    # Normaliser les UUIDs et IDs pour regrouper les endpoints
    normalized = _normalize_path(path)
    rec = RequestRecord(
        path=normalized,
        method=method.upper(),
        status_code=status_code,
        duration_ms=duration_ms,
    )
    with _lock:
        _buffer.append(rec)
        _counts[f"{method.upper()}:{normalized}"] += 1


def get_performance_stats(top_n: int = 20) -> dict:
    """
    Calcule les statistiques de performance à partir du buffer.
    Retourne les top_n endpoints les plus appelés avec p50/p95/p99/avg.
    """
    with _lock:
        records = list(_buffer)

    if not records:
        return {
            "total_requests": 0,
            "buffer_size": BUFFER_SIZE,
            "endpoints": [],
            "slow_requests": [],
        }

    # Grouper par (method, path)
    groups: dict[str, list[float]] = defaultdict(list)
    errors: dict[str, int]         = defaultdict(int)
    for r in records:
        key = f"{r.method}:{r.path}"
        groups[key].append(r.duration_ms)
        if r.status_code >= 500:
            errors[key] += 1

    # Calculer les percentiles pour chaque groupe
    endpoints = []
    for key, durations in groups.items():
        method, path = key.split(":", 1)
        sorted_d = sorted(durations)
        n = len(sorted_d)
        endpoints.append({
            "method":    method,
            "path":      path,
            "count":     n,
            "avg_ms":    round(statistics.mean(sorted_d), 1),
            "p50_ms":    round(_percentile(sorted_d, 50), 1),
            "p95_ms":    round(_percentile(sorted_d, 95), 1),
            "p99_ms":    round(_percentile(sorted_d, 99), 1),
            "max_ms":    round(max(sorted_d), 1),
            "error_5xx": errors[key],
            "slow_pct":  round(100 * sum(1 for d in sorted_d if d > SLOW_THRESHOLD_MS) / n, 1),
        })

    # Trier par nombre d'appels décroissant, limiter à top_n
    endpoints.sort(key=lambda e: e["count"], reverse=True)
    endpoints = endpoints[:top_n]

    # Top 5 requêtes les plus lentes (parmi le buffer récent)
    slow_requests = sorted(records, key=lambda r: r.duration_ms, reverse=True)[:5]

    return {
        "total_requests":   len(records),
        "buffer_size":      BUFFER_SIZE,
        "slow_threshold_ms": SLOW_THRESHOLD_MS,
        "endpoints":        endpoints,
        "slow_requests": [
            {
                "method":      r.method,
                "path":        r.path,
                "status_code": r.status_code,
                "duration_ms": round(r.duration_ms, 1),
                "ts":          r.ts.isoformat(),
            }
            for r in slow_requests
        ],
    }


def reset_metrics() -> None:
    """Vide le buffer (utile pour les tests)."""
    with _lock:
        _buffer.clear()
        _counts.clear()


# ─── Helpers privés ───────────────────────────────────────────────────────────

def _percentile(sorted_data: list[float], p: int) -> float:
    """Calcule le p-ième percentile d'une liste triée."""
    if not sorted_data:
        return 0.0
    idx = (p / 100) * (len(sorted_data) - 1)
    lo  = int(idx)
    hi  = min(lo + 1, len(sorted_data) - 1)
    frac = idx - lo
    return sorted_data[lo] + frac * (sorted_data[hi] - sorted_data[lo])


_UUID_RE = __import__("re").compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"|[0-9a-f]{32}"
    r"|\b\d{4,}\b",
    __import__("re").IGNORECASE,
)


def _normalize_path(path: str) -> str:
    """
    Remplace les UUIDs et IDs numériques par des placeholders
    pour regrouper les endpoints du type /scans/history/abc-123.
    """
    # Supprimer les query strings
    path = path.split("?")[0]
    # UUID complet ou hexadécimal de 32 chars → {uuid}
    path = _UUID_RE.sub("{id}", path)
    return path
