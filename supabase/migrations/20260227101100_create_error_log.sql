-- System error log for debugging and monitoring.
-- Backend-only via service_role (Option B). RLS ON, no policies.
CREATE TABLE public.error_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID REFERENCES public.analysis_runs(id) ON DELETE SET NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    component VARCHAR(50) NOT NULL,
    error_type VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    resolved BOOLEAN NOT NULL DEFAULT false
);

ALTER TABLE public.error_log ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_error_log_analysis_id ON public.error_log(analysis_id);
CREATE INDEX idx_error_log_timestamp ON public.error_log(timestamp DESC);
