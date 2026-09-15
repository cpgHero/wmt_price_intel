"""Customer authentication routes backed by WorkOS AuthKit."""

from __future__ import annotations

import json
from html import escape
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response

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


def _callback_complete_response(return_to: str) -> HTMLResponse:
    """Commit the CPGHero session cookie before entering protected app routes.

    Chrome can fail to present freshly set cookies on the immediate next hop when
    an OAuth callback both sets cookies and responds with another server-side
    redirect. Returning a tiny first-party document gives the browser a stable
    CPGHero response to store the cookie before the same-origin navigation.
    """

    safe_return = safe_return_path(return_to)
    safe_return_json = json.dumps(safe_return)
    retry_url = f"/api/auth/login?return_to={quote(safe_return, safe='')}"
    escaped_retry_url = escape(retry_url, quote=True)
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Finishing sign-in · CPGHero</title>
  <style>
    :root {{
      color-scheme: dark;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
    }}
    body {{
      min-height: 100vh;
      margin: 0;
      display: grid;
      place-items: center;
      background: radial-gradient(
          circle at 18% 12%,
          rgba(82, 230, 198, 0.18),
          transparent 30rem
        ),
        #071115;
      color: #eef8fb;
    }}
    main {{
      width: min(32rem, calc(100vw - 2rem));
      border: 1px solid rgba(148, 178, 190, 0.28);
      border-radius: 1.25rem;
      background: rgba(12, 28, 36, 0.9);
      box-shadow: 0 2rem 5rem rgba(0, 0, 0, 0.4);
      padding: 2rem;
    }}
    .brand {{
      color: #5fe6c8;
      font-size: 0.72rem;
      font-weight: 850;
      letter-spacing: 0.16em;
      text-transform: uppercase;
    }}
    h1 {{
      font-size: clamp(1.7rem, 5vw, 2.4rem);
      letter-spacing: -0.06em;
      line-height: 1;
      margin: 0.55rem 0 0.8rem;
    }}
    p {{ color: #abc1cb; line-height: 1.55; margin: 0; }}
    a {{ color: #5fe6c8; font-weight: 800; }}
    .detail {{ margin-top: 1rem; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 0.8rem; margin-top: 1.4rem; }}
    .button {{
      align-items: center;
      border: 1px solid rgba(95, 230, 200, 0.45);
      border-radius: 999px;
      display: inline-flex;
      padding: 0.65rem 0.9rem;
      text-decoration: none;
    }}
    .button.secondary {{
      border-color: rgba(148, 178, 190, 0.28);
      color: #abc1cb;
    }}
    .hidden {{ display: none; }}
  </style>
</head>
<body>
  <main>
    <div class="brand">CPGHero customer access</div>
    <h1>Finishing sign-in.</h1>
    <p id="status-message">
      Your customer session has been created. Verifying CPGHero access before opening the app.
    </p>
    <p id="error-message" class="detail hidden">
      CPGHero could not read the new customer session in this browser. Automatic retries have
      been stopped to avoid identity-provider rate limits.
    </p>
    <div id="manual-actions" class="actions hidden">
      <a class="button" href="{escaped_retry_url}">Try sign-in again</a>
      <a class="button secondary" href="/">Return to public home</a>
    </div>
  </main>
  <script>
    (async () => {{
      const destination = {safe_return_json};
      const statusMessage = document.getElementById("status-message");
      const errorMessage = document.getElementById("error-message");
      const actions = document.getElementById("manual-actions");
      try {{
        const response = await fetch("/api/auth/me", {{
          cache: "no-store",
          credentials: "include",
          headers: {{ accept: "application/json" }},
        }});
        if (response.ok) {{
          window.location.replace(destination);
          return;
        }}
      }} catch (error) {{
        // Fall through to the controlled manual-retry state.
      }}
      statusMessage.textContent =
        "Sign-in reached CPGHero, but the customer session is not readable yet.";
      errorMessage.classList.remove("hidden");
      actions.classList.remove("hidden");
    }})();
  </script>
</body>
</html>""",
        status_code=status.HTTP_200_OK,
        headers={"cache-control": "private, no-store"},
    )


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
) -> Response:
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
    complete_response = _callback_complete_response(completed.return_to)
    set_customer_cookie(
        complete_response,
        settings=request.app.state.settings,
        name=SESSION_COOKIE_NAME,
        value=completed.sealed_session,
        max_age=SESSION_MAX_AGE_SECONDS,
    )
    complete_response.delete_cookie(FLOW_COOKIE_NAME, path="/")
    return complete_response


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
