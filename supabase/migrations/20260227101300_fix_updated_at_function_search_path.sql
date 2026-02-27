-- Fix: Supabase Security Advisor WARN "function_search_path_mutable".
-- Migration 0 was initially applied without SET search_path = ''.
-- This migration fixed it. The local file for migration 0 was retroactively
-- updated to include the fix, making this a no-op on fresh installs.
-- Kept for consistency with Supabase migration history.
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = '';
