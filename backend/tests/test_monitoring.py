"""Tests for the monitoring service (src/services/monitoring.py).

Mocks get_supabase_admin to avoid real DB calls. Covers:
- Data present (happy path)
- Empty DB (no runs)
- DB error (fail-open returns zeros)
- Batching for large .in_() queries
"""

from unittest.mock import MagicMock, patch

from src.services.monitoring import get_system_metrics

USER_ID = "test-user-id-123"


def _make_admin_mock(runs=None, claims=None, verifications=None):
    """Build supabase admin mock with name-based table routing."""
    admin = MagicMock()

    # analysis_runs chain: .select().eq().gte().execute()
    runs_chain = MagicMock()
    runs_chain.select.return_value = runs_chain
    runs_chain.eq.return_value = runs_chain
    runs_chain.gte.return_value = runs_chain
    runs_resp = MagicMock()
    runs_resp.data = runs
    runs_chain.execute.return_value = runs_resp

    # claims chain: .select().in_().execute()
    claims_chain = MagicMock()
    claims_chain.select.return_value = claims_chain
    claims_chain.in_.return_value = claims_chain
    claims_resp = MagicMock()
    claims_resp.data = claims
    claims_chain.execute.return_value = claims_resp

    # verification_results chain: .select().in_().execute()
    verif_chain = MagicMock()
    verif_chain.select.return_value = verif_chain
    verif_chain.in_.return_value = verif_chain
    verif_resp = MagicMock()
    verif_resp.data = verifications
    verif_chain.execute.return_value = verif_resp

    # Name-based dispatch (robust regardless of call count/order)
    table_map = {
        "analysis_runs": runs_chain,
        "claims": claims_chain,
        "verification_results": verif_chain,
    }
    admin.table.side_effect = lambda name: table_map[name]

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

    @patch("src.services.monitoring.get_supabase_admin")
    @patch("src.services.monitoring._IN_BATCH_SIZE", 3)
    def test_in_query_batched_for_large_lists(self, mock_admin):
        """Verify .in_() is called in batches when list exceeds batch size."""
        runs = [
            {
                "id": f"run-{i}",
                "status": "completed",
                "started_at": "2026-03-01T10:00:00+00:00",
                "completed_at": "2026-03-01T10:01:00+00:00",
            }
            for i in range(5)
        ]
        claims = [
            {"id": f"claim-{i}", "analysis_id": f"run-{i % 5}"} for i in range(7)
        ]
        verifications = [{"status": "verified"} for _ in range(7)]

        admin = _make_admin_mock(runs, claims, verifications)
        mock_admin.return_value = admin

        result = get_system_metrics(USER_ID)

        # 5 analysis_ids, batch_size=3 → ceil(5/3) = 2 claims batches
        claims_calls = [
            c for c in admin.table.call_args_list if c[0][0] == "claims"
        ]
        verif_calls = [
            c for c in admin.table.call_args_list if c[0][0] == "verification_results"
        ]
        assert len(claims_calls) == 2  # ceil(5/3) = 2
        # Mock returns full list per batch (no real filtering), so verification
        # batches depend on accumulated claim_ids. Key assertion: >1 batch.
        assert len(verif_calls) > 1
        assert result["verification_score"]["verified"] > 0
