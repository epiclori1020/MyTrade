-- T-020: Remove ineffective INSERT policy on policy_change_log.
-- Backend uses service_role (Option B) which bypasses RLS.
-- Keeping the policy creates a false sense of security.
-- SELECT policy remains (users can read their own audit trail).
DROP POLICY IF EXISTS "Users can insert own policy change log" ON public.policy_change_log;
