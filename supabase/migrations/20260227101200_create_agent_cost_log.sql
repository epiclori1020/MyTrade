-- API cost tracking per agent call (3-Tier Model-Mix).
-- Backend-only via service_role (Option B). RLS ON, no policies.
CREATE TABLE public.agent_cost_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID REFERENCES public.analysis_runs(id) ON DELETE SET NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    agent_name VARCHAR(50) NOT NULL,
    model VARCHAR(50) NOT NULL,
    tier VARCHAR(10) NOT NULL CHECK (tier IN ('heavy', 'standard', 'light')),
    effort VARCHAR(10) NOT NULL DEFAULT 'medium'
        CHECK (effort IN ('low', 'medium', 'high')),
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd DECIMAL(8,4) NOT NULL,
    fallback_from VARCHAR(50),
    degraded BOOLEAN NOT NULL DEFAULT false
);

ALTER TABLE public.agent_cost_log ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_agent_cost_log_analysis_id ON public.agent_cost_log(analysis_id);
CREATE INDEX idx_agent_cost_log_timestamp ON public.agent_cost_log(timestamp DESC);
