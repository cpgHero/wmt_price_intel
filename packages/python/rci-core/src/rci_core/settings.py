"""Environment-backed settings shared by every service."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_APP_ENV = "development"
DEFAULT_APP_VERSION = "0.1.0"
DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/rci"
DEFAULT_LOG_LEVEL = "INFO"


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Non-secret service settings.

    Secret values remain in environment variables and are never serialized or logged.
    """

    app_env: str = DEFAULT_APP_ENV
    app_version: str = DEFAULT_APP_VERSION
    database_url: str = DEFAULT_DATABASE_URL
    log_level: str = DEFAULT_LOG_LEVEL

    @classmethod
    def from_env(cls) -> AppSettings:
        return cls(
            app_env=os.getenv("APP_ENV", DEFAULT_APP_ENV),
            app_version=os.getenv("APP_VERSION", DEFAULT_APP_VERSION),
            database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
            log_level=os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
        )

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"
