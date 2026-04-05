"""Shared base settings for all Omur services."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    """Common env vars shared across all Omur backend services.

    Subclass this in each service and add service-specific fields.
    Pydantic-settings maps UPPERCASE env vars to these fields automatically.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Omur runtime
    OMUR_MODE: str = "standalone"
    OMUR_TENANT_TOKEN: str = ""

    # CORS
    CORS_ORIGINS: str = "https://omur.local,http://localhost:3000"

    # PostgreSQL
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "omur"
    POSTGRES_USER: str = "omur"
    POSTGRES_PASSWORD: str = ""

    # Valkey (Redis-compatible, Apache 2.0)
    VALKEY_HOST: str = "redis"  # compose service name runs Valkey 9.0
    VALKEY_PORT: int = 6379

    # Ollama
    OLLAMA_HOST: str = "http://ollama:11434"
    OLLAMA_CHAT_MODEL: str = "qwen3:8b"
    OLLAMA_EMBED_MODEL: str = "bge-m3"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def postgres_dsn_raw(self) -> str:
        """Plain postgresql:// DSN for drivers that don't accept asyncpg dialect."""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def valkey_url(self) -> str:
        return f"redis://{self.VALKEY_HOST}:{self.VALKEY_PORT}"
