"""Tests for the monitoring service (src/services/monitoring.py).

Mocks get_supabase_admin to avoid real DB calls. Covers:
- Data present (happy path)
- Empty DB (no runs)
- DB error (fail-open returns zeros)
"""

from unittest.mock import MagicMock, patch

from src.services.monitoring import get_system_metrics

USER_ID = "test-user-id-123"


def _make_admin_mock(runs=None, claims=None, verifications=None):
    """Build a chained supabase admin mock.

    Returns the mock so individual table().select()... can be verified.
    """
    admin = MagicMock()

    # analysis_runs chain
    runs_chain = MagicMock()
    runs_chain.select.return_value = runs_chain
    runs_chain.eq.return_value = runs_chain
    runs_chain.gte.return_value = runs_chain
    runs_resp = MagicMock()
    runs_resp.data = runs
    runs_chain.execute.return_value = runs_resp

    # claims chain
    claims_chain = MagicMock()
    claims_chain.select.return_value = claims_chain
    claims_chain.in_.return_value = claims_chain
    claims_resp = MagicMock()
    claims_resp.data = claims
    claims_chain.execute.return_value = claims_resp

    # verification_results chain
    verif_chain = MagicMock()
    verif_chain.select.return_value = verif_chain
    verif_chain.in_.return_value = verif_chain
    verif_resp = MagicMock()
    verif_resp.data = verifications
    verif_chain.execute.return_value = verif_resp

    # Route table() calls to the right chain
    call_count = {"n": 0}
    chains = [runs_chain, claims_chain, verif_chain]

    def table_side_effect(name):
        idx = min(call_count["n"], len(chains) - 1)
        call_count["n"] += 1
        return chains[idx]

    admin.table.side_effect = table_side_effect
    return admin


class TestGetSystemMetrics:
    @patch("src.services.monitoring.get_supabase_admin")
    def test_happy_path_with_data(self, mock_admin):
        runs = [
            {
                "id": "run-1",
                "status": "completed",
                "started_at": "2026-03-01T10:00:00+00:00",
                "completed_at": "2026-03-01T10:01:30+00:00",
            },
            {
                "id": "run-2",
                "status": "failed",
                "started_at": "2026-03-02T12:00:00+00:00",
                "completed_at": None,
            },
        ]
        claims = [
            {"id": "claim-1", "analysis_id": "run-1"},
            {"id": "claim-2", "analysis_id": "run-1"},
            {"id": "claim-3", "analysis_id": "run-1"},
        ]
        verifications = [
            {"status": "verified"},
            {"status": "consistent"},
            {"status": "disputed"},
        ]

        mock_admin.return_value = _make_admin_mock(runs, claims, verifications)
        result = get_system_metrics(USER_ID)

        # Pipeline error rate: 1 failed / 2 total = 50%
        assert result["pipeline_error_rate"]["rate_pct"] == 50.0
        assert result["pipeline_error_rate"]["failed"] == 1
        assert result["pipeline_error_rate"]["total"] == 2

        # Avg latency: only run-1 has completed_at → 90s
        assert result["avg_latency_seconds"]["value"] == 90.0
        assert result["avg_latency_seconds"]["total_runs"] == 1

        # Verification: 2/3 verified+consistent = 66.7%
        assert result["verification_score"]["rate_pct"] == 66.7
        assert result["verification_score"]["verified"] == 2
        assert result["verification_score"]["total"] == 3

    @patch("src.services.monitoring.get_supabase_admin")
    def test_empty_db_returns_zeros(self, mock_admin):
        mock_admin.return_value = _make_admin_mock(runs=[], claims=[], verifications=[])
        result = get_system_metrics(USER_ID)

        assert result["pipeline_error_rate"]["rate_pct"] == 0.0
        assert result["pipeline_error_rate"]["total"] == 0
        assert result["avg_latency_seconds"]["value"] == 0.0
        assert result["verification_score"]["rate_pct"] == 0.0

    @patch("src.services.monitoring.get_supabase_admin")
    def test_db_error_returns_zeros_failopen(self, mock_admin):
        mock_admin.side_effect = Exception("DB connection lost")
        result = get_system_metrics(USER_ID)

        assert result["pipeline_error_rate"]["rate_pct"] == 0.0
        assert result["pipeline_error_rate"]["detail"] == "Metrics unavailable"
        assert result["avg_latency_seconds"]["value"] == 0.0
        assert result["verification_score"]["rate_pct"] == 0.0

    @patch("src.services.monitoring.get_supabase_admin")
    def test_all_runs_completed_zero_error_rate(self, mock_admin):
        runs = [
            {
                "id": "run-1",
                "status": "completed",
                "started_at": "2026-03-01T10:00:00+00:00",
                "completed_at": "2026-03-01T10:02:00+00:00",
            },
            {
                "id": "run-2",
                "status": "completed",
                "started_at": "2026-03-02T12:00:00+00:00",
                "completed_at": "2026-03-02T12:00:45+00:00",
            },
        ]
        mock_admin.return_value = _make_admin_mock(runs, claims=[], verifications=[])
        result = get_system_metrics(USER_ID)

        assert result["pipeline_error_rate"]["rate_pct"] == 0.0
        assert result["pipeline_error_rate"]["failed"] == 0
        assert result["pipeline_error_rate"]["total"] == 2
        # Avg latency: (120 + 45) / 2 = 82.5s
        assert result["avg_latency_seconds"]["value"] == 82.5
