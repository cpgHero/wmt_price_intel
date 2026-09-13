"""Environment-backed settings shared by every service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import cast

from rci_core.identity import CustomerIdentityProviderConfig, IdentityProviderKey

DEFAULT_APP_ENV = "development"
DEFAULT_APP_VERSION = "0.1.0"
DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/rci"
DEFAULT_LOG_LEVEL = "INFO"


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    return value.strip() or None


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Non-secret service settings.

    Secret values remain in environment variables and are never serialized or logged.
    """

    app_env: str = DEFAULT_APP_ENV
    app_version: str = DEFAULT_APP_VERSION
    database_url: str = DEFAULT_DATABASE_URL
    log_level: str = DEFAULT_LOG_LEVEL
    customer_identity_provider: IdentityProviderKey = "disabled"
    workos_client_id: str | None = None
    workos_redirect_uri: str | None = None

    @classmethod
    def from_env(cls) -> AppSettings:
        provider = os.getenv("CPGHERO_CUSTOMER_AUTH_PROVIDER", "disabled").strip().lower()
        if provider not in {"disabled", "workos"}:
            raise ValueError("CPGHERO_CUSTOMER_AUTH_PROVIDER must be one of: disabled, workos")
        customer_identity_provider = cast(IdentityProviderKey, provider)
        return cls(
            app_env=os.getenv("APP_ENV", DEFAULT_APP_ENV),
            app_version=os.getenv("APP_VERSION", DEFAULT_APP_VERSION),
            database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
            log_level=os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
            customer_identity_provider=customer_identity_provider,
            workos_client_id=_optional_env("WORKOS_CLIENT_ID"),
            workos_redirect_uri=_optional_env("WORKOS_REDIRECT_URI"),
        )

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def customer_auth(self) -> CustomerIdentityProviderConfig:
        return CustomerIdentityProviderConfig(
            provider=self.customer_identity_provider,
            workos_client_id=self.workos_client_id,
            workos_redirect_uri=self.workos_redirect_uri,
        )
