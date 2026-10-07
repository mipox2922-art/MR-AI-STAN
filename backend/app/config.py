from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MR AI — Digital Chief of Staff"
    secret_key: str = "CHANGE_THIS_SECRET_KEY"
    access_token_expire_minutes: int = 60 * 24

    database_url: str = "sqlite:///./mr_ai.db"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_tier: str = "FREE"

    kimi_api_key: str = ""
    kimi_model: str = "kimi-k2"

    kimi_base_url: str = "https://api.moonshot.ai/v1"

    cors_origins: str = "http://localhost:5173"
    searxng_url: str = ""

    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_redirect_uri: str = ""
    gmail_scopes: str = "https://www.googleapis.com/auth/gmail.readonly"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
