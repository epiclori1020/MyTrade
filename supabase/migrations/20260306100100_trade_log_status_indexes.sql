-- T-029: Partial indexes for lazy maintenance queries.
-- expire_stale_trades() filters: status='proposed', proposed_at < cutoff
-- cleanup_orphaned_trades() filters: status='approved', approved_at < cutoff
-- Partial indexes: smaller than composite, exact match for WHERE status = '...' queries.
CREATE INDEX IF NOT EXISTS idx_trade_log_status_proposed
    ON public.trade_log(proposed_at DESC)
    WHERE status = 'proposed';

CREATE INDEX IF NOT EXISTS idx_trade_log_status_approved
    ON public.trade_log(approved_at DESC)
    WHERE status = 'approved';
