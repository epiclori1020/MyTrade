-- Fix trade_log: Add status default + column immutability trigger
-- Addresses CodeRabbit findings:
--   1. UPDATE policy allows mutation of all columns during approve/reject
--   2. status column missing DEFAULT 'proposed'

-- Part 1: Status default — defensive programming best practice
ALTER TABLE public.trade_log ALTER COLUMN status SET DEFAULT 'proposed';

-- Part 2: Column immutability trigger
-- When a user approves/rejects a trade (proposed → approved/rejected),
-- only status, approved_at, and rejection_reason may change.
-- Trade details (ticker, shares, price, etc.) are immutable.
-- Note: This trigger fires for ALL roles including service_role.
-- The condition OLD.status = 'proposed' ensures backend transitions
-- (approved → executed) are not restricted.
CREATE OR REPLACE FUNCTION public.enforce_trade_log_immutable_fields()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    -- Only enforce during user-facing transition: proposed → approved/rejected
    IF OLD.status = 'proposed' AND NEW.status IN ('approved', 'rejected') THEN
        IF NEW.user_id     IS DISTINCT FROM OLD.user_id
        OR NEW.analysis_id IS DISTINCT FROM OLD.analysis_id
        OR NEW.ticker      IS DISTINCT FROM OLD.ticker
        OR NEW.action      IS DISTINCT FROM OLD.action
        OR NEW.shares      IS DISTINCT FROM OLD.shares
        OR NEW.price       IS DISTINCT FROM OLD.price
        OR NEW.order_type  IS DISTINCT FROM OLD.order_type
        OR NEW.stop_loss   IS DISTINCT FROM OLD.stop_loss
        OR NEW.broker      IS DISTINCT FROM OLD.broker
        OR NEW.broker_order_id IS DISTINCT FROM OLD.broker_order_id
        OR NEW.proposed_at IS DISTINCT FROM OLD.proposed_at
        THEN
            RAISE EXCEPTION 'Cannot modify trade details during approval. Only status, approved_at, and rejection_reason may change.';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_trade_log_immutable_fields
    BEFORE UPDATE ON public.trade_log
    FOR EACH ROW
    EXECUTE FUNCTION public.enforce_trade_log_immutable_fields();
