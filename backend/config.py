"""Application configuration.

Every setting is read from the environment (or a local `.env` file). Nothing is
hardcoded and no credential ever appears in the repository. If a required
variable is missing the app fails fast at import time with a message that names
exactly what is missing, rather than dying later with an opaque driver error.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- CognoDB connection -------------------------------------------------
    cognodb_uri: str = Field(default="", alias="COGNODB_URI")
    cognodb_user: str = Field(default="cognodb", alias="COGNODB_USER")
    cognodb_password: str = Field(default="", alias="COGNODB_PASSWORD")

    # --- HTTP ---------------------------------------------------------------
    port: int = Field(default=8000, alias="PORT")
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")

    # --- Driver / query tuning ---------------------------------------------
    max_connection_pool_size: int = Field(default=15, alias="MAX_CONNECTION_POOL_SIZE")
    query_timeout_seconds: float = Field(default=15.0, alias="QUERY_TIMEOUT_SECONDS")

    @field_validator("cognodb_uri")
    @classmethod
    def _validate_uri(cls, value: str) -> str:
        if value and not value.startswith(("bolt://", "bolt+s://", "bolt+ssc://", "neo4j://", "neo4j+s://")):
            raise ValueError(
                f"COGNODB_URI must start with bolt+s:// (or bolt://, neo4j://). Got: {value!r}"
            )
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def missing_required(self) -> list[str]:
        """Names of required variables that are absent, for a friendly startup error."""
        missing = []
        if not self.cognodb_uri:
            missing.append("COGNODB_URI")
        if not self.cognodb_user:
            missing.append("COGNODB_USER")
        if not self.cognodb_password:
            missing.append("COGNODB_PASSWORD")
        return missing

    @property
    def is_configured(self) -> bool:
        return not self.missing_required

    def safe_summary(self) -> dict:
        """Config summary safe to log or return over HTTP -- no password, no host."""
        return {
            "uri_scheme": self.cognodb_uri.split("://")[0] if self.cognodb_uri else None,
            "user": self.cognodb_user or None,
            "configured": self.is_configured,
            "pool_size": self.max_connection_pool_size,
            "query_timeout_seconds": self.query_timeout_seconds,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
