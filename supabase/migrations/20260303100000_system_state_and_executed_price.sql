-- Step 11: Kill-Switch + Budget-Fallback
-- Creates system_state table (single-row, global) for Kill-Switch state
-- and adds executed_price column to trade_log.

-- system_state: single-row table for MVP (global, not per-user)
CREATE TABLE system_state (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kill_switch_active BOOLEAN NOT NULL DEFAULT false,
  kill_switch_reason TEXT,
  kill_switch_activated_at TIMESTAMPTZ,
  highwater_mark_value DECIMAL(12,4),
  highwater_mark_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed with fixed UUID (idempotent)
INSERT INTO system_state (id)
VALUES ('00000000-0000-0000-0000-000000000001'::uuid)
ON CONFLICT (id) DO NOTHING;

-- RLS: authenticated SELECT only, writes via service_role
ALTER TABLE system_state ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Authenticated users can read system state"
  ON system_state FOR SELECT USING (auth.role() = 'authenticated');

-- Add executed_price to trade_log (nullable — only set after execution)
ALTER TABLE trade_log ADD COLUMN IF NOT EXISTS executed_price DECIMAL(12,4);
