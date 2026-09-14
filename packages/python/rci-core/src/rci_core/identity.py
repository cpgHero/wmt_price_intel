"""Identity-provider configuration and mapping primitives.

Authentication is intentionally separate from authorization. WorkOS AuthKit can
prove who a user is, while CPGHero-owned account, workspace, role, entitlement,
project, usage, and billing records decide what that user can access.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

IdentityProviderKey = Literal["disabled", "workos"]
ExternalIdentitySubjectType = Literal["user", "organization"]

WORKOS_AUTH_ENV_VARS: tuple[str, ...] = (
    "WORKOS_CLIENT_ID",
    "WORKOS_API_KEY",
    "WORKOS_COOKIE_PASSWORD",
    "WORKOS_REDIRECT_URI",
)

WORKOS_WEBHOOK_ENV_VARS: tuple[str, ...] = ("WORKOS_WEBHOOK_SECRET",)

WORKOS_CANARY_ENV_VARS: tuple[str, ...] = (
    "CPGHERO_CUSTOMER_AUTH_CANARY_ENABLED",
    "CPGHERO_CUSTOMER_AUTH_ALLOWED_EMAILS",
    "CPGHERO_CUSTOMER_AUTH_ALLOWED_DOMAINS",
)


@dataclass(frozen=True, slots=True)
class CustomerIdentityProviderConfig:
    """Non-secret customer authentication configuration.

    Secret values such as WorkOS API keys, cookie passwords, and webhook
    secrets remain in process environment variables and must not be serialized
    into API responses, client bundles, reports, or logs.
    """

    provider: IdentityProviderKey = "disabled"
    workos_client_id: str | None = None
    workos_redirect_uri: str | None = None
    canary_enabled: bool = False
    allowed_email_count: int = 0
    allowed_domain_count: int = 0

    @property
    def is_enabled(self) -> bool:
        return self.provider != "disabled"

    @property
    def uses_workos(self) -> bool:
        return self.provider == "workos"

    @property
    def required_env_vars(self) -> tuple[str, ...]:
        if not self.uses_workos:
            return ()
        return WORKOS_AUTH_ENV_VARS


@dataclass(frozen=True, slots=True)
class ExternalIdentityReference:
    """Provider identity reference bound to a CPGHero-owned principal record."""

    provider: Literal["workos"]
    subject_type: ExternalIdentitySubjectType
    subject_id: str
    cpg_user_id: str | None = None
    cpg_account_id: str | None = None

    def __post_init__(self) -> None:
        if not self.subject_id.strip():
            raise ValueError("external identity subject_id is required")
        if self.subject_type == "user" and not self.cpg_user_id:
            raise ValueError("user external identities require cpg_user_id")
        if self.subject_type == "organization" and not self.cpg_account_id:
            raise ValueError("organization external identities require cpg_account_id")
