from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    readonly_database_url: str
    allow_sql_writes: bool = False
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    uploads_dir: str = "/uploads"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
