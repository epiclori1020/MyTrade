-- Attach updated_at trigger to system_state table.
-- The trigger function update_updated_at_column() already exists
-- (created in 20260227100000_create_updated_at_trigger_function.sql).
-- This makes system_state consistent with user_policy and portfolio_holdings.

CREATE TRIGGER set_system_state_updated_at
  BEFORE UPDATE ON system_state
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();
