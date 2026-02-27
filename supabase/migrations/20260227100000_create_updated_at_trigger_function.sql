-- Shared trigger function for auto-updating updated_at columns.
-- Used by: user_policy, portfolio_holdings.
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = '';
