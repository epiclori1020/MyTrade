-- Audit trail for all IPS policy changes.
-- Source: docs/02_policy/settings-spec.md (authoritative)
CREATE TABLE public.policy_change_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    old_mode TEXT,
    new_mode TEXT,
    old_preset TEXT,
    new_preset TEXT,
    old_overrides JSONB,
    new_overrides JSONB,
    change_reason TEXT DEFAULT NULL
);

ALTER TABLE public.policy_change_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own policy change log"
    ON public.policy_change_log FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own policy change log"
    ON public.policy_change_log FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE INDEX idx_policy_change_log_user_id ON public.policy_change_log(user_id);
CREATE INDEX idx_policy_change_log_changed_at ON public.policy_change_log(changed_at DESC);
