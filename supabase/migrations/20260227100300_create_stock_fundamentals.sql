-- Fundamental data per ticker/period from data providers.
-- Shared data: authenticated users can read, only service_role writes.
CREATE TABLE public.stock_fundamentals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker VARCHAR(10) NOT NULL,
    period VARCHAR(7) NOT NULL,
    revenue BIGINT,
    net_income BIGINT,
    free_cash_flow BIGINT,
    total_debt BIGINT,
    total_equity BIGINT,
    eps DECIMAL(10,4),
    pe_ratio DECIMAL(10,2),
    pb_ratio DECIMAL(10,2),
    ev_ebitda DECIMAL(10,2),
    roe DECIMAL(8,4),
    roic DECIMAL(8,4),
    f_score INTEGER CHECK (f_score BETWEEN 0 AND 9),
    z_score DECIMAL(6,3),
    source VARCHAR(50) NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT stock_fundamentals_ticker_period_source_unique UNIQUE (ticker, period, source)
);

ALTER TABLE public.stock_fundamentals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated users can read stock fundamentals"
    ON public.stock_fundamentals FOR SELECT
    TO authenticated
    USING (true);

CREATE INDEX idx_stock_fundamentals_ticker_period ON public.stock_fundamentals(ticker, period);
