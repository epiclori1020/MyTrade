-- Current portfolio positions (paper + future live).
-- Backend creates via service_role; user reads/updates own holdings.
CREATE TABLE public.portfolio_holdings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    ticker VARCHAR(10) NOT NULL,
    shares DECIMAL(12,4) NOT NULL,
    avg_price DECIMAL(12,4) NOT NULL,
    current_price DECIMAL(12,4),
    weight_pct DECIMAL(5,2),
    entry_date DATE NOT NULL,
    stop_loss DECIMAL(12,4),
    thesis TEXT,
    asset_class VARCHAR(20) NOT NULL DEFAULT 'equity',
    is_core BOOLEAN NOT NULL DEFAULT false,
    status VARCHAR(10) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'sold', 'stopped_out')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.portfolio_holdings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own holdings"
    ON public.portfolio_holdings FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can update own holdings"
    ON public.portfolio_holdings FOR UPDATE
    USING (auth.uid() = user_id);

CREATE TRIGGER set_portfolio_holdings_updated_at
    BEFORE UPDATE ON public.portfolio_holdings
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

CREATE INDEX idx_portfolio_holdings_user_id ON public.portfolio_holdings(user_id);
CREATE INDEX idx_portfolio_holdings_ticker ON public.portfolio_holdings(ticker);
