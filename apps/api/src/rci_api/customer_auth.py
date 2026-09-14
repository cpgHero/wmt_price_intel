"""Customer authentication routes backed by WorkOS AuthKit."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from rci_api.customer_identity import _customer_authenticator
from rci_api.workos_auth import (
    FLOW_COOKIE_NAME,
    FLOW_MAX_AGE_SECONDS,
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    safe_return_path,
    set_customer_cookie,
)

router = APIRouter(prefix="/api/auth", tags=["customer-auth"])


@router.get("/login")
def login(
    request: Request,
    return_to: Annotated[str | None, Query(alias="return_to")] = None,
) -> RedirectResponse:
    authenticator = _customer_authenticator(request)
    login_start = authenticator.start_login(return_to=return_to or "/")
    response = RedirectResponse(url=login_start.authorization_url, status_code=307)
    set_customer_cookie(
        response,
        settings=request.app.state.settings,
        name=FLOW_COOKIE_NAME,
        value=login_start.flow_cookie,
        max_age=FLOW_MAX_AGE_SECONDS,
    )
    return response


@router.get("/callback")
def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WorkOS callback requires code and state.",
        )
    flow_cookie = request.cookies.get(FLOW_COOKIE_NAME)
    if not flow_cookie:
        response = RedirectResponse(
            url="/api/auth/login?return_to=/customer&auth_restart=missing_flow",
            status_code=status.HTTP_303_SEE_OTHER,
        )
        response.delete_cookie(FLOW_COOKIE_NAME, path="/")
        return response
    authenticator = _customer_authenticator(request)
    completed = authenticator.complete_login(
        code=code,
        state=state,
        flow_cookie=flow_cookie,
        request=request,
    )
    response = RedirectResponse(url=completed.return_to, status_code=303)
    set_customer_cookie(
        response,
        settings=request.app.state.settings,
        name=SESSION_COOKIE_NAME,
        value=completed.sealed_session,
        max_age=SESSION_MAX_AGE_SECONDS,
    )
    response.delete_cookie(FLOW_COOKIE_NAME, path="/")
    return response


@router.get("/logout")
def logout(
    request: Request,
    return_to: Annotated[str | None, Query(alias="return_to")] = None,
) -> RedirectResponse:
    authenticator = _customer_authenticator(request)
    safe_return = safe_return_path(return_to)
    logout_url = authenticator.get_logout_url(
        session_cookie=request.cookies.get(SESSION_COOKIE_NAME),
        return_to=safe_return,
    )
    response = RedirectResponse(url=logout_url or safe_return, status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(FLOW_COOKIE_NAME, path="/")
    return response
