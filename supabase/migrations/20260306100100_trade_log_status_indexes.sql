-- T-029: Composite indexes for lazy maintenance queries.
-- expire_stale_trades() filters: status='proposed', proposed_at < cutoff
-- cleanup_orphaned_trades() filters: status='approved', approved_at < cutoff
CREATE INDEX IF NOT EXISTS idx_trade_log_status_proposed
    ON public.trade_log(status, proposed_at DESC);

CREATE INDEX IF NOT EXISTS idx_trade_log_status_approved
    ON public.trade_log(status, approved_at DESC);
