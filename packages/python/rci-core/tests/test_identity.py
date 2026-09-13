from __future__ import annotations

import pytest

from rci_core import AppSettings
from rci_core.identity import (
    WORKOS_AUTH_ENV_VARS,
    CustomerIdentityProviderConfig,
    ExternalIdentityReference,
)


def test_customer_auth_defaults_to_disabled_without_workos_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CPGHERO_CUSTOMER_AUTH_PROVIDER", raising=False)
    monkeypatch.delenv("WORKOS_CLIENT_ID", raising=False)
    monkeypatch.delenv("WORKOS_REDIRECT_URI", raising=False)

    settings = AppSettings.from_env()

    assert settings.customer_auth == CustomerIdentityProviderConfig()
    assert settings.customer_auth.is_enabled is False
    assert settings.customer_auth.required_env_vars == ()


def test_workos_auth_provider_exposes_only_non_secret_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CPGHERO_CUSTOMER_AUTH_PROVIDER", "workos")
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_123")
    monkeypatch.setenv("WORKOS_API_KEY", "sk_test_must_not_serialize")
    monkeypatch.setenv("WORKOS_COOKIE_PASSWORD", "cookie-secret")
    monkeypatch.setenv("WORKOS_REDIRECT_URI", "https://app.cpghero.com/api/auth/callback")
    monkeypatch.setenv("WORKOS_WEBHOOK_SECRET", "whsec_secret")

    config = AppSettings.from_env().customer_auth

    assert config.uses_workos
    assert config.is_enabled
    assert config.workos_client_id == "client_123"
    assert config.workos_redirect_uri == "https://app.cpghero.com/api/auth/callback"
    assert config.required_env_vars == WORKOS_AUTH_ENV_VARS
    assert "sk_test_must_not_serialize" not in repr(config)
    assert "cookie-secret" not in repr(config)
    assert "whsec_secret" not in repr(config)


def test_unknown_customer_auth_provider_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CPGHERO_CUSTOMER_AUTH_PROVIDER", "custom-passwords")

    with pytest.raises(
        ValueError,
        match="CPGHERO_CUSTOMER_AUTH_PROVIDER must be one of: disabled, workos",
    ):
        AppSettings.from_env()


def test_external_identity_reference_requires_cpg_bindings() -> None:
    user_reference = ExternalIdentityReference(
        provider="workos",
        subject_type="user",
        subject_id="user_123",
        cpg_user_id="00000000-0000-0000-0000-000000000301",
    )
    organization_reference = ExternalIdentityReference(
        provider="workos",
        subject_type="organization",
        subject_id="org_123",
        cpg_account_id="00000000-0000-0000-0000-000000000101",
    )

    assert user_reference.subject_id == "user_123"
    assert organization_reference.subject_id == "org_123"

    with pytest.raises(ValueError, match="user external identities require cpg_user_id"):
        ExternalIdentityReference(
            provider="workos",
            subject_type="user",
            subject_id="user_123",
        )

    with pytest.raises(
        ValueError,
        match="organization external identities require cpg_account_id",
    ):
        ExternalIdentityReference(
            provider="workos",
            subject_type="organization",
            subject_id="org_123",
        )
