-- Macroeconomic indicators (GDP, CPI, Fed Rate, etc.).
-- Shared data: authenticated users can read, only service_role writes.
CREATE TABLE public.macro_indicators (
    date DATE NOT NULL,
    gdp DECIMAL(15,2),
    cpi DECIMAL(8,4),
    fed_rate DECIMAL(5,4),
    yield_spread DECIMAL(6,4),
    pmi DECIMAL(6,2),
    unemployment DECIMAL(5,2),
    source VARCHAR(50) NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (date, source)
);

ALTER TABLE public.macro_indicators ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated users can read macro indicators"
    ON public.macro_indicators FOR SELECT
    TO authenticated
    USING (true);
