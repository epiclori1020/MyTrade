"""System metrics aggregation for the monitoring dashboard.

Queries analysis_runs and verification_results (via claims) for pipeline
health metrics. Uses supabase_admin (service_role) + explicit user_id
filter — same Option B pattern as kill_switch.py.

Fail-open: returns zeros on DB error (non-critical metrics).
"""

import logging
from datetime import datetime, timezone, timedelta

from src.services.supabase import get_supabase_admin

logger = logging.getLogger(__name__)

_IN_BATCH_SIZE = 500


def _batched_in_query(admin, table: str, select: str, column: str, values: list) -> list:
    """Run .in_() queries in batches to avoid PostgREST URL length limits."""
    results = []
    for i in range(0, len(values), _IN_BATCH_SIZE):
        batch = values[i : i + _IN_BATCH_SIZE]
        resp = admin.table(table).select(select).in_(column, batch).execute()
        results.extend(resp.data or [])
    return results


def get_system_metrics(user_id: str) -> dict:
    """Aggregated system metrics from analysis_runs (last 30 days).

    Returns: {
        pipeline_error_rate: {rate_pct, failed, total, detail},
        avg_latency_seconds: {value, total_runs, detail},
        verification_score: {rate_pct, verified, total, detail}
    }
    """
    try:
        admin = get_supabase_admin()
        since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

        # --- Pipeline error rate + avg latency from analysis_runs ---
        runs_resp = (
            admin.table("analysis_runs")
            .select("id, status, started_at, completed_at")
            .eq("user_id", user_id)
            .gte("started_at", since)
            .execute()
        )
        runs = runs_resp.data or []
        total_runs = len(runs)
        failed_runs = sum(1 for r in runs if r.get("status") == "failed")

        error_rate = round(
            (failed_runs / total_runs * 100) if total_runs > 0 else 0.0, 1
        )

        # Avg latency for completed runs
        latencies = []
        for r in runs:
            if r.get("completed_at") and r.get("started_at"):
                try:
                    start = datetime.fromisoformat(r["started_at"])
                    end = datetime.fromisoformat(r["completed_at"])
                    latencies.append((end - start).total_seconds())
                except (ValueError, TypeError):
                    pass

        avg_latency = round(
            sum(latencies) / len(latencies) if latencies else 0.0, 1
        )

        # --- Verification score from verification_results ---
        # Get analysis IDs for this user in the time window
        analysis_ids = [r.get("id") for r in runs if r.get("id")]

        verified_count = 0
        total_claims = 0

        if analysis_ids:
            # Get claims for these analyses (batched for PostgREST URL limits)
            claim_rows = _batched_in_query(
                admin, "claims", "id, analysis_id", "analysis_id", analysis_ids
            )
            total_claims = len(claim_rows)

            if claim_rows:
                claim_ids = [c["id"] for c in claim_rows]
                # Get verification results (batched)
                verif_rows = _batched_in_query(
                    admin, "verification_results", "status", "claim_id", claim_ids
                )
                verified_count = sum(
                    1 for v in verif_rows
                    if v.get("status") in ("verified", "consistent")
                )

        verif_rate = round(
            (verified_count / total_claims * 100) if total_claims > 0 else 0.0,
            1,
        )

        return {
            "pipeline_error_rate": {
                "rate_pct": error_rate,
                "failed": failed_runs,
                "total": total_runs,
                "detail": f"{failed_runs}/{total_runs} runs failed (30d)",
            },
            "avg_latency_seconds": {
                "value": avg_latency,
                "total_runs": len(latencies),
                "detail": f"Avg {avg_latency}s over {len(latencies)} completed runs",
            },
            "verification_score": {
                "rate_pct": verif_rate,
                "verified": verified_count,
                "total": total_claims,
                "detail": f"{verified_count}/{total_claims} claims verified/consistent",
            },
        }
    except Exception as exc:
        logger.warning("Failed to get system metrics — fail-open: %s", exc)
        return {
            "pipeline_error_rate": {
                "rate_pct": 0.0,
                "failed": 0,
                "total": 0,
                "detail": "Metrics unavailable",
            },
            "avg_latency_seconds": {
                "value": 0.0,
                "total_runs": 0,
                "detail": "Metrics unavailable",
            },
            "verification_score": {
                "rate_pct": 0.0,
                "verified": 0,
                "total": 0,
                "detail": "Metrics unavailable",
            },
        }
