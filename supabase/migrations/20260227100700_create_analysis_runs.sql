-- Analysis runs with agent outputs. One row per ticker analysis.
-- Backend creates via service_role; user reads own runs via JWT.
CREATE TABLE public.analysis_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    ticker VARCHAR(10) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed', 'partial')),
    macro_output JSONB,
    fundamental_out JSONB,
    technical_out JSONB,
    sentiment_out JSONB,
    risk_output JSONB,
    devil_output JSONB,
    synthesis_out JSONB,
    verification JSONB,
    recommendation VARCHAR(20),
    confidence INTEGER CHECK (confidence BETWEEN 0 AND 100),
    trade_proposed BOOLEAN NOT NULL DEFAULT false,
    total_tokens INTEGER,
    total_cost_usd DECIMAL(8,4),
    error_log JSONB NOT NULL DEFAULT '[]'::jsonb
);

ALTER TABLE public.analysis_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own analysis runs"
    ON public.analysis_runs FOR SELECT
    USING (auth.uid() = user_id);

CREATE INDEX idx_analysis_runs_user_ticker ON public.analysis_runs(user_id, ticker);
CREATE INDEX idx_analysis_runs_started_at ON public.analysis_runs(started_at DESC);
