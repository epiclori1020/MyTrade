-- Historical and current stock prices with technical indicators.
-- Shared data: authenticated users can read, only service_role writes.
CREATE TABLE public.stock_prices (
    ticker VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(12,4),
    high DECIMAL(12,4),
    low DECIMAL(12,4),
    close DECIMAL(12,4),
    volume BIGINT,
    rsi DECIMAL(6,2),
    macd DECIMAL(10,4),
    atr DECIMAL(10,4),
    source VARCHAR(50) NOT NULL,
    PRIMARY KEY (ticker, date)
);

ALTER TABLE public.stock_prices ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated users can read stock prices"
    ON public.stock_prices FOR SELECT
    TO authenticated
    USING (true);
