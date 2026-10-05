"""Settings loaded from environment variables (Token Factory, Nebius Sandboxes, Tavily, Supabase, GitHub, Postgres)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database: required, e.g. postgresql+asyncpg://mux:mux@localhost:5433/mux (the docker-compose Postgres)
    database_url: str = ""
    test_database_url: str = ""
    debug: bool = False

    # Token Factory
    token_factory_api_key: str = ""
    token_factory_base_url: str = ""
    model_lightning: str = ""
    model_super: str = ""
    model_ultra: str = ""

    # Nebius Sandboxes
    sandbox_api_key: str = ""
    sandbox_base_url: str = ""
    sandbox_image: str = ""

    # Tavily
    tavily_api_key: str = ""

    # Supabase
    supabase_jwt_secret: str = ""
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_audience: str = ""
    supabase_jwt_issuer: str = ""
    # Allow unverified JWT tokens (local development only - NEVER enable in production)
    allow_unverified_tokens: bool = False

    # GitHub OAuth
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = ""
    github_token_encryption_key: str = ""


settings = Settings()
