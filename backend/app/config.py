from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration, overridable via environment or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "TinyProtocol"
    stage: str = "dev"
    table_name: str = "TinyProtocol-dev"

    jwt_secret: str = "dev-secret-change-me"
    jwt_expiry_days: int = 90

    # Point at DynamoDB Local for development (e.g. http://localhost:8000).
    dynamo_endpoint_url: str | None = None

    # "*" is fine while it's just the two of us.
    cors_origins: str = "*"


settings = Settings()
