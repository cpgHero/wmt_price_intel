# Phase 14.28 Customer auth session-readiness guard

## Scope

Customer AuthKit callback hardening for the production customer-login canary.

## Change

Successful `/api/auth/callback` responses still set the CPGHero customer-session cookie on a private first-party completion page, but the page no longer enters a protected app route unconditionally.

The completion page now calls the same-origin `/api/auth/me` endpoint with browser credentials first. It navigates to the validated return path only after CPGHero can read and validate the customer session. If that validation fails, the page stops on a controlled CPGHero message with manual retry and public-home links instead of automatically re-entering hosted login.

Production customer-session cookies now use the same callback-compatible `SameSite=None; Secure` attributes as the temporary login-flow cookie. Local and development cookies remain `SameSite=Lax` unless production security settings are active.

## Rationale

The prior completion page proved that WorkOS accepted the login and the CPGHero API created a session, but production logs still showed the browser immediately requesting `/api/auth/login?return_to=/customer` again after the completion page. There were no intervening `/api/auth/me` or `/api/v1/me` validation calls, which means the protected route boundary did not see the `cph_customer_session` cookie.

This change addresses both sides of the remaining failure mode:

- make the production session cookie compatible with the hosted Google → AuthKit → CPGHero callback path;
- prevent a failed session handoff from becoming a rapid identity-provider redirect loop and rate-limit storm.

## Verification

- `apps/api/tests/test_customer_identity.py` verifies the callback completion page:
  - returns `200`
  - remains `private, no-store`
  - sets the CPGHero customer-session cookie
  - clears the temporary login-flow cookie
  - checks `/api/auth/me` before navigation
  - exposes manual recovery links instead of automatic retry when the session is not readable
  - uses production `SameSite=None; Secure` cookie attributes for customer auth cookies

## Explicit non-goals

This does not change WorkOS credentials, WorkOS user provisioning, canary allowlists, roles, entitlements, account/workspace authorization, report calculations, proximity metrics, collection requests, source-provider calls, PDP calls, AI calls, PDFs, or historical artifacts.

Before broad customer write APIs are exposed, state-changing customer routes should add explicit anti-CSRF controls appropriate for cross-site-compatible session cookies.
