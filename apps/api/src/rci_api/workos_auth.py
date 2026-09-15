"""WorkOS AuthKit session bridge for CPGHero customer authentication."""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Protocol, cast

from cryptography.fernet import Fernet
from fastapi import HTTPException, Request, Response, status
from workos import WorkOSClient
from workos.session import (
    AuthenticateWithSessionCookieSuccessResponse,
    RefreshWithSessionCookieSuccessResponse,
    seal_data,
    seal_session_from_auth_response,
    unseal_data,
)

from rci_core import AppSettings

SESSION_COOKIE_NAME = "cph_customer_session"
FLOW_COOKIE_NAME = "cph_customer_auth_flow"
FLOW_MAX_AGE_SECONDS = 10 * 60
SESSION_MAX_AGE_SECONDS = 8 * 60 * 60


@dataclass(frozen=True, slots=True)
class WorkOSLoginStart:
    authorization_url: str
    flow_cookie: str


@dataclass(frozen=True, slots=True)
class WorkOSLoginComplete:
    sealed_session: str
    return_to: str


@dataclass(frozen=True, slots=True)
class WorkOSSessionIdentity:
    workos_user_id: str
    email: str
    workos_organization_id: str | None = None
    session_id: str | None = None
    sealed_session: str | None = None
    refreshed: bool = False


class CustomerSessionAuthenticator(Protocol):
    def start_login(self, *, return_to: str) -> WorkOSLoginStart: ...

    def complete_login(
        self,
        *,
        code: str,
        state: str,
        flow_cookie: str,
        request: Request,
    ) -> WorkOSLoginComplete: ...

    def authenticate_session_cookie(
        self,
        *,
        session_cookie: str | None,
        request: Request,
    ) -> WorkOSSessionIdentity: ...

    def get_logout_url(
        self, *, session_cookie: str | None, return_to: str | None
    ) -> str | None: ...


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{name} is required before WorkOS customer authentication can run.",
        )
    return value


def _cookie_password() -> str:
    value = _required_env("WORKOS_COOKIE_PASSWORD")
    try:
        Fernet(value.encode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "WORKOS_COOKIE_PASSWORD must be a Fernet-compatible key generated with "
                "Fernet.generate_key() or an equivalent urlsafe base64 32-byte key."
            ),
        ) from exc
    return value


def safe_return_path(value: str | None) -> str:
    if not value:
        return "/"
    stripped = value.strip()
    if not stripped.startswith("/") or stripped.startswith("//"):
        return "/"
    return stripped


def _extract_client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        candidate = forwarded_for.split(",", maxsplit=1)[0].strip()
        if candidate:
            return candidate
    if request.client:
        return request.client.host
    return None


def _user_value(user: object, key: str) -> str | None:
    value = user.get(key) if isinstance(user, dict) else getattr(user, key, None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _user_dict(user: object) -> dict[str, Any]:
    if isinstance(user, dict):
        return user
    to_dict = getattr(user, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, dict):
            return result
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="WorkOS authentication response did not include a usable user.",
    )


class WorkOSCustomerSessionAuthenticator:
    """Resolve WorkOS AuthKit redirects and sealed-session cookies."""

    def __init__(
        self,
        *,
        client: WorkOSClient,
        redirect_uri: str,
        cookie_password: str,
        canary_enabled: bool,
        allowed_emails: tuple[str, ...],
        allowed_domains: tuple[str, ...],
    ) -> None:
        self._client = client
        self._redirect_uri = redirect_uri
        self._cookie_password = cookie_password
        self._canary_enabled = canary_enabled
        self._allowed_emails = frozenset(email.lower() for email in allowed_emails)
        self._allowed_domains = frozenset(
            domain.removeprefix("@").lower() for domain in allowed_domains
        )

    @classmethod
    def from_env(cls, settings: AppSettings) -> WorkOSCustomerSessionAuthenticator:
        if settings.customer_identity_provider != "workos":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer authentication is disabled.",
            )
        client_id = settings.workos_client_id or _required_env("WORKOS_CLIENT_ID")
        api_key = _required_env("WORKOS_API_KEY")
        redirect_uri = settings.workos_redirect_uri or _required_env("WORKOS_REDIRECT_URI")
        return cls(
            client=WorkOSClient(api_key=api_key, client_id=client_id),
            redirect_uri=redirect_uri,
            cookie_password=_cookie_password(),
            canary_enabled=settings.customer_auth_canary_enabled,
            allowed_emails=settings.customer_auth_allowed_emails,
            allowed_domains=settings.customer_auth_allowed_domains,
        )

    def start_login(self, *, return_to: str) -> WorkOSLoginStart:
        pair = self._client.pkce.generate()
        state = secrets.token_urlsafe(32)
        flow_cookie = seal_data(
            {
                "state": state,
                "code_verifier": pair.code_verifier,
                "return_to": safe_return_path(return_to),
                "created_at": int(time.time()),
            },
            self._cookie_password,
        )
        authorization_url = self._client.user_management.get_authorization_url(
            provider="authkit",
            redirect_uri=self._redirect_uri,
            state=state,
            code_challenge=pair.code_challenge,
            code_challenge_method=pair.code_challenge_method,
        )
        return WorkOSLoginStart(authorization_url=authorization_url, flow_cookie=flow_cookie)

    def complete_login(
        self,
        *,
        code: str,
        state: str,
        flow_cookie: str,
        request: Request,
    ) -> WorkOSLoginComplete:
        flow = self._load_flow_cookie(flow_cookie, expected_state=state)
        auth_response = self._client.user_management.authenticate_with_code(
            code=code,
            code_verifier=cast("str", flow["code_verifier"]),
            ip_address=_extract_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        auth_payload = auth_response.to_dict()
        user_payload = cast("dict[str, Any]", auth_payload["user"])
        self._assert_canary_user_allowed(user_payload)
        sealed_session = seal_session_from_auth_response(
            access_token=auth_response.access_token,
            refresh_token=auth_response.refresh_token,
            user=user_payload,
            impersonator=cast("dict[str, Any] | None", auth_payload.get("impersonator")),
            cookie_password=self._cookie_password,
        )
        return WorkOSLoginComplete(
            sealed_session=sealed_session,
            return_to=safe_return_path(cast("str | None", flow.get("return_to"))),
        )

    def authenticate_session_cookie(
        self,
        *,
        session_cookie: str | None,
        request: Request,
    ) -> WorkOSSessionIdentity:
        if not session_cookie:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Customer authentication is required.",
            )
        session = self._client.user_management.load_sealed_session(
            session_data=session_cookie,
            cookie_password=self._cookie_password,
        )
        result = session.authenticate()
        if not result.authenticated:
            refreshed = session.refresh()
            if not isinstance(refreshed, RefreshWithSessionCookieSuccessResponse):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Customer session is invalid or expired.",
                )
            user = _user_dict(refreshed.user)
            return self._identity_from_values(
                user=user,
                session_id=refreshed.session_id,
                organization_id=refreshed.organization_id,
                sealed_session=refreshed.sealed_session,
                refreshed=True,
            )
        if not isinstance(result, AuthenticateWithSessionCookieSuccessResponse):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Customer session is invalid or expired.",
            )
        user = _user_dict(result.user)
        return self._identity_from_values(
            user=user,
            session_id=result.session_id,
            organization_id=result.organization_id,
            sealed_session=None,
            refreshed=False,
        )

    def get_logout_url(self, *, session_cookie: str | None, return_to: str | None) -> str | None:
        if not session_cookie:
            return None
        session = self._client.user_management.load_sealed_session(
            session_data=session_cookie,
            cookie_password=self._cookie_password,
        )
        try:
            return session.get_logout_url(return_to=return_to)
        except Exception:
            return None

    def _load_flow_cookie(self, flow_cookie: str, *, expected_state: str) -> dict[str, str | int]:
        try:
            flow = unseal_data(flow_cookie, self._cookie_password)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Customer authentication flow is invalid or expired.",
            ) from exc
        state = flow.get("state")
        code_verifier = flow.get("code_verifier")
        created_at = flow.get("created_at")
        if not isinstance(state, str) or not secrets.compare_digest(state, expected_state):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Customer authentication state did not match.",
            )
        if not isinstance(code_verifier, str) or not code_verifier:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Customer authentication flow is invalid or expired.",
            )
        if not isinstance(created_at, int) or time.time() - created_at > FLOW_MAX_AGE_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Customer authentication flow is invalid or expired.",
            )
        return cast("dict[str, str | int]", flow)

    def _identity_from_values(
        self,
        *,
        user: dict[str, Any],
        session_id: str,
        organization_id: str | None,
        sealed_session: str | None,
        refreshed: bool,
    ) -> WorkOSSessionIdentity:
        workos_user_id = _user_value(user, "id")
        email = _user_value(user, "email")
        if not workos_user_id or not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="WorkOS session did not include a usable user identity.",
            )
        return WorkOSSessionIdentity(
            workos_user_id=workos_user_id,
            email=email,
            workos_organization_id=organization_id,
            session_id=session_id,
            sealed_session=sealed_session,
            refreshed=refreshed,
        )

    def _assert_canary_user_allowed(self, user: dict[str, Any]) -> None:
        if not self._canary_enabled:
            return
        email = (_user_value(user, "email") or "").lower()
        domain = email.rsplit("@", maxsplit=1)[-1] if "@" in email else ""
        if not self._allowed_emails and not self._allowed_domains:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "CPGHero customer login canary is enabled, but no allowed users or domains "
                    "are configured."
                ),
            )
        if email in self._allowed_emails or domain in self._allowed_domains:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This CPGHero customer login canary is limited to approved users.",
        )


def set_customer_cookie(
    response: Response,
    *,
    settings: AppSettings,
    name: str,
    value: str,
    max_age: int,
) -> None:
    response.set_cookie(
        name,
        value,
        httponly=True,
        secure=settings.is_production,
        samesite=(
            "none"
            if settings.is_production and name in {FLOW_COOKIE_NAME, SESSION_COOKIE_NAME}
            else "lax"
        ),
        path="/",
        max_age=max_age,
    )
