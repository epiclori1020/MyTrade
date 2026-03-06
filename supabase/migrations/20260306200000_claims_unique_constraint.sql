-- T-019: Prevent duplicate claims for the same analysis.
-- claim_id is deterministic ({analysis_id}_{001}) — duplicates indicate
-- re-extraction without prior cleanup. This makes re-extraction fail
-- gracefully instead of creating duplicates.
CREATE UNIQUE INDEX IF NOT EXISTS idx_claims_analysis_claim_id
    ON public.claims(analysis_id, claim_id);
