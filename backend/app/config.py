from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MR AI — Digital Chief of Staff"
    secret_key: str = "CHANGE_THIS_SECRET_KEY"
    access_token_expire_minutes: int = 60 * 24
    serverless_mode: bool = False

    database_url: str = "sqlite:///./mr_ai.db"
    database_ssl_ca_cert: str = ""

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


MIN_SECRET_KEY_LENGTH = 32
INSECURE_SECRET_KEYS = frozenset({
    "",
    "CHANGE_ME_TO_A_LONG_RANDOM_SECRET",
    "CHANGE_THIS_SECRET_KEY",
})


def validate_secret_key(secret_key: str) -> None:
    """Reject default or short JWT keys before starting the API."""
    candidate = secret_key.strip()
    if candidate in INSECURE_SECRET_KEYS or len(candidate) < MIN_SECRET_KEY_LENGTH:
        raise RuntimeError(
            "SECRET_KEY must be a unique random value of at least 32 characters. "
            "Run start.sh to generate a local key or configure SECRET_KEY in the hosting environment."
        )


settings = Settings()
