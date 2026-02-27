-- IPS settings per user (3-Tier: Beginner/Preset/Advanced).
-- Source: docs/02_policy/settings-spec.md (authoritative)
CREATE TABLE public.user_policy (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    policy_mode TEXT NOT NULL DEFAULT 'BEGINNER'
        CHECK (policy_mode IN ('BEGINNER', 'PRESET', 'ADVANCED')),
    preset_id TEXT NOT NULL DEFAULT 'beginner'
        CHECK (preset_id IN ('beginner', 'balanced', 'active')),
    policy_overrides JSONB NOT NULL DEFAULT '{}'::jsonb,
    cooldown_until TIMESTAMPTZ DEFAULT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT user_policy_user_id_unique UNIQUE (user_id)
);

ALTER TABLE public.user_policy ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own policy"
    ON public.user_policy FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can update own policy"
    ON public.user_policy FOR UPDATE
    USING (auth.uid() = user_id);

CREATE TRIGGER set_user_policy_updated_at
    BEFORE UPDATE ON public.user_policy
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

CREATE INDEX idx_user_policy_user_id ON public.user_policy(user_id);
