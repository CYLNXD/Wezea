"""
Tests unitaires — app/metrics.py
Pure logique : aucun réseau, aucune DB.
"""
import pytest
from app.metrics import record_request, get_performance_stats, reset_metrics, _normalize_path, _percentile


@pytest.fixture(autouse=True)
def clear_metrics():
    """Vide le buffer avant chaque test."""
    reset_metrics()
    yield
    reset_metrics()


# ─────────────────────────────────────────────────────────────────────────────
# _normalize_path
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizePath:
    def test_plain_path_unchanged(self):
        assert _normalize_path("/auth/login") == "/auth/login"

    def test_uuid_replaced(self):
        result = _normalize_path("/scans/history/550e8400-e29b-41d4-a716-446655440000")
        assert "{id}" in result
        assert "550e8400" not in result

    def test_numeric_id_replaced(self):
        result = _normalize_path("/admin/users/12345")
        assert "{id}" in result
        assert "12345" not in result

    def test_query_string_stripped(self):
        result = _normalize_path("/admin/purge-scans?retention_days=30")
        assert "?" not in result
        assert "30" not in result

    def test_short_numbers_not_replaced(self):
        """Les petits nombres (< 4 chiffres) ne doivent PAS être remplacés."""
        result = _normalize_path("/api/v1/scan")
        assert result == "/api/v1/scan"


# ─────────────────────────────────────────────────────────────────────────────
# _percentile
# ─────────────────────────────────────────────────────────────────────────────

class TestPercentile:
    def test_p50_middle(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _percentile(data, 50) == 3.0

    def test_p100_max(self):
        data = [10.0, 20.0, 30.0]
        assert _percentile(data, 100) == 30.0

    def test_empty_returns_zero(self):
        assert _percentile([], 50) == 0.0

    def test_single_element(self):
        assert _percentile([42.0], 95) == 42.0


# ─────────────────────────────────────────────────────────────────────────────
# record_request / get_performance_stats
# ─────────────────────────────────────────────────────────────────────────────

class TestRecordAndStats:
    def test_empty_buffer_returns_zero(self):
        stats = get_performance_stats()
        assert stats["total_requests"] == 0
        assert stats["endpoints"] == []

    def test_single_request_recorded(self):
        record_request("/auth/login", "POST", 200, 45.0)
        stats = get_performance_stats()
        assert stats["total_requests"] == 1
        assert len(stats["endpoints"]) == 1
        ep = stats["endpoints"][0]
        assert ep["path"] == "/auth/login"
        assert ep["method"] == "POST"
        assert ep["count"] == 1
        assert ep["avg_ms"] == 45.0

    def test_multiple_requests_aggregated(self):
        for ms in [100.0, 200.0, 300.0]:
            record_request("/scan", "POST", 200, ms)
        stats = get_performance_stats()
        ep = stats["endpoints"][0]
        assert ep["count"] == 3
        assert ep["avg_ms"] == 200.0

    def test_health_path_skipped(self):
        record_request("/health", "GET", 200, 1.0)
        stats = get_performance_stats()
        assert stats["total_requests"] == 0

    def test_5xx_counted(self):
        record_request("/scan", "POST", 500, 100.0)
        record_request("/scan", "POST", 200, 50.0)
        stats = get_performance_stats()
        ep = stats["endpoints"][0]
        assert ep["error_5xx"] == 1

    def test_slow_pct_computed(self):
        # 1 requête rapide + 1 lente (> 500ms)
        record_request("/scan", "POST", 200, 100.0)
        record_request("/scan", "POST", 200, 800.0)
        stats = get_performance_stats()
        ep = stats["endpoints"][0]
        assert ep["slow_pct"] == 50.0

    def test_sorted_by_count_desc(self):
        # /a appelé 3 fois, /b appelé 1 fois
        for _ in range(3):
            record_request("/a", "GET", 200, 10.0)
        record_request("/b", "GET", 200, 10.0)
        stats = get_performance_stats()
        assert stats["endpoints"][0]["path"] == "/a"
        assert stats["endpoints"][1]["path"] == "/b"

    def test_top5_slow_requests(self):
        # 6 requêtes : la plus lente doit apparaître en tête
        for ms in [100, 200, 300, 400, 500, 999]:
            record_request("/scan", "POST", 200, float(ms))
        stats = get_performance_stats()
        slow = stats["slow_requests"]
        assert len(slow) <= 5
        assert slow[0]["duration_ms"] == 999.0

    def test_p95_greater_than_p50(self):
        for ms in range(1, 101):
            record_request("/scan", "POST", 200, float(ms))
        stats = get_performance_stats()
        ep = stats["endpoints"][0]
        assert ep["p95_ms"] > ep["p50_ms"]

    def test_method_uppercase(self):
        record_request("/scan", "post", 200, 50.0)
        stats = get_performance_stats()
        assert stats["endpoints"][0]["method"] == "POST"
