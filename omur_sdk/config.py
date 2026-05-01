"""packages/omur-sdk/omur_sdk/config.py — Shared base settings for all Omur services.

exports: class BaseServiceSettings
used_by: none
rules:   The module requires all backend services to share a common BaseSettings class for consistent environment variable handling, and all service configurations must be derived from this base with no deviation in the configuration inheritance structure.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""

from pydantic import Field
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
    omur_settings_key: str = Field(default="", alias="OMUR_SETTINGS_KEY")

    # CORS
    CORS_ORIGINS: str = "https://omur.local,http://localhost:3000"

    # PostgreSQL
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "omur"
    POSTGRES_USER: str = "omur"
    POSTGRES_PASSWORD: str = ""

    # Valkey (Redis-compatible, Apache 2.0)
    VALKEY_HOST: str = "valkey"
    VALKEY_PORT: int = 6379
    VALKEY_PASSWORD: str = ""

    # Ollama
    OLLAMA_HOST: str = "http://ollama:11434"
    OLLAMA_CHAT_MODEL: str = "qwen3:8b"
    OLLAMA_EMBED_MODEL: str = "bge-m3"

    @property
    def postgres_dsn(self) -> str:
        """
        Rules:   none
        """
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def postgres_dsn_raw(self) -> str:
        """Plain postgresql:// DSN for drivers that don't accept asyncpg dialect.

        Rules:   none
        """
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def valkey_url(self) -> str:
        """
        Rules:   When VALKEY_PASSWORD is set, the Redis URL must include the password in the format redis://:password@host:port. If not set, the URL should omit the password field entirely.
        """
        if self.VALKEY_PASSWORD:
            return f"redis://:{self.VALKEY_PASSWORD}@{self.VALKEY_HOST}:{self.VALKEY_PORT}"
        return f"redis://{self.VALKEY_HOST}:{self.VALKEY_PORT}"
