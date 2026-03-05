from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Reads from the root .env file (one level above backend/).
    Required variables must be set or the app will fail on startup
    with a clear Pydantic ValidationError.
    """

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Required: Supabase ---
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # --- Optional: Supabase Direct DB (needed from Step 8+ for Agno PostgreSQL Storage) ---
    supabase_db_url: str = ""

    # --- Optional: LLM ---
    anthropic_api_key: str = ""

    # --- Optional: Data Providers ---
    finnhub_api_key: str = ""
    alpha_vantage_api_key: str = ""

    # --- Optional: Broker (Stufe 1 = Paper only) ---
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_paper_mode: bool = True

    # --- App Config ---
    cors_origins: str = "http://localhost:3000"
    environment: str = "development"
    log_level: str = "INFO"

    # --- Admin ---
    admin_user_ids: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        """Split comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def admin_user_id_list(self) -> list[str]:
        """Split comma-separated admin user IDs into a list."""
        return [uid.strip() for uid in self.admin_user_ids.split(",") if uid.strip()]


@lru_cache
def get_settings() -> Settings:
    """Singleton settings instance. Cached after first call."""
    return Settings()
