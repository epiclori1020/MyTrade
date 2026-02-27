-- Widen stock_fundamentals.period from VARCHAR(7) to VARCHAR(20)
-- to accommodate period formats like "2026-TTM" (8 chars).
ALTER TABLE public.stock_fundamentals ALTER COLUMN period TYPE VARCHAR(20);
