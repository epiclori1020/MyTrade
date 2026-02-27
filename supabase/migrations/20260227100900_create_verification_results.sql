-- Verification results per claim (cross-check against second data source).
-- Backend-only via service_role (Option B). RLS ON, no policies.
CREATE TABLE public.verification_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES public.claims(id) ON DELETE CASCADE,
    source_verification JSONB NOT NULL,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('verified', 'consistent', 'unverified', 'disputed', 'manual_check')),
    confidence_adjustment INTEGER NOT NULL DEFAULT 0,
    verified_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.verification_results ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_verification_results_claim_id ON public.verification_results(claim_id);
CREATE INDEX idx_verification_results_status ON public.verification_results(status);
