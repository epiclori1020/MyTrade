-- T-017: Circuit Breaker persistence columns on system_state.
-- Alpaca breaker state survives server restarts.
ALTER TABLE public.system_state
    ADD COLUMN IF NOT EXISTS cb_state TEXT DEFAULT 'closed',
    ADD COLUMN IF NOT EXISTS cb_failure_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS cb_last_failure_time FLOAT DEFAULT 0.0;
