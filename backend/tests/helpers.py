from src.config import Settings


def make_test_settings() -> Settings:
    """Settings override for tests. No real env vars or .env file needed."""
    return Settings(
        supabase_url="https://test.supabase.co",
        supabase_anon_key="test-anon-key",
        supabase_service_role_key="test-service-role-key",
        cors_origins="http://localhost:3000",
        finnhub_api_key="test-finnhub-key",
        alpha_vantage_api_key="test-av-key",
    )
