-- Extracted claims from agent outputs, validated against claim-schema.json.
-- Backend-only via service_role (Option B). RLS ON, no policies.
CREATE TABLE public.claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES public.analysis_runs(id) ON DELETE CASCADE,
    claim_id VARCHAR(50) NOT NULL,
    claim_text TEXT NOT NULL,
    claim_type VARCHAR(20) NOT NULL
        CHECK (claim_type IN ('number', 'ratio', 'event', 'opinion', 'forecast')),
    value DECIMAL(20,4),
    unit VARCHAR(20),
    ticker VARCHAR(10),
    period VARCHAR(20),
    source_primary JSONB NOT NULL,
    tier VARCHAR(5) NOT NULL CHECK (tier IN ('A', 'B', 'C')),
    required_tier VARCHAR(10) NOT NULL CHECK (required_tier IN ('A', 'A+B', 'B', 'C')),
    trade_critical BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.claims ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_claims_analysis_id ON public.claims(analysis_id);
CREATE INDEX idx_claims_ticker ON public.claims(ticker);
