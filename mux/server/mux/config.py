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


settings = Settings()
