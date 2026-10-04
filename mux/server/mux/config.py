"""Settings loaded from environment variables (Token Factory, Nebius Sandboxes, Tavily, Supabase, GitHub, Postgres)."""

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file = ".env", extra="ignore")

    token_factory_api_key:str = ""
    token_factory_base_url:str = ""
    model_lightning:str = ""
    model_super:str = ""
    model_ultra:str = ""
    tavily_api_key:str = ""
    database_url:str = ""
    test_database_url:str = ""
    sandbox_api_key:str = ""
    sandbox_base_url:str = ""
    sandbox_image:str = ""


settings = Settings()
