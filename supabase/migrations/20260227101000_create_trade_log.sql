-- Trade proposals and executions.
-- Backend creates via service_role. User reads own trades via JWT.
-- Special UPDATE policy: only proposed -> approved/rejected allowed.
CREATE TABLE public.trade_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    analysis_id UUID REFERENCES public.analysis_runs(id) ON DELETE SET NULL,
    ticker VARCHAR(10) NOT NULL,
    action VARCHAR(4) NOT NULL CHECK (action IN ('BUY', 'SELL')),
    shares DECIMAL(12,4) NOT NULL,
    price DECIMAL(12,4) NOT NULL,
    order_type VARCHAR(10) NOT NULL DEFAULT 'LIMIT',
    stop_loss DECIMAL(12,4),
    status VARCHAR(15) NOT NULL
        CHECK (status IN ('proposed', 'approved', 'rejected', 'executed', 'failed')),
    broker VARCHAR(10),
    broker_order_id VARCHAR(50),
    proposed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    rejection_reason TEXT
);

ALTER TABLE public.trade_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own trades"
    ON public.trade_log FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can approve or reject proposed trades"
    ON public.trade_log FOR UPDATE
    USING (auth.uid() = user_id AND status = 'proposed')
    WITH CHECK (status IN ('approved', 'rejected'));

CREATE INDEX idx_trade_log_user_proposed ON public.trade_log(user_id, proposed_at DESC);
