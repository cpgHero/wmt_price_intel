# Phase 14.10 — Customer-auth canary guardrails and readiness cockpit

## Objective

Add the next safe rollout layer for customer authentication without enabling broad production
customer login.

This phase exists because the first real WorkOS invitation flow proved the webhook path can
deliver, but also showed that customer-facing browser failures were too raw and that readiness was
only visible through database/Railway probes. The application now needs explicit canary controls and
an internal go/no-go surface before cutover.

## Implemented

- Added customer-auth canary settings:
  - `CPGHERO_CUSTOMER_AUTH_CANARY_ENABLED`
  - `CPGHERO_CUSTOMER_AUTH_ALLOWED_EMAILS`
  - `CPGHERO_CUSTOMER_AUTH_ALLOWED_DOMAINS`
- Made the WorkOS callback fail closed when the canary is enabled:
  - if no allowlist is configured, the callback returns a service-unavailable error;
  - if the authenticated email/domain is not allowlisted, the callback returns forbidden;
  - if the user is allowlisted, normal CPGHero session sealing and principal resolution continue.
- Added a protected API readiness endpoint:
  - `GET /api/v1/admin/customer-provisioning/readiness`
  - guarded by the existing platform-admin control;
  - reports internal provider state, canary configuration, cutover blockers, invitation readiness,
    and recent signed identity webhook processing.
- Added a protected web admin page:
  - `Administration > Customer Auth`
  - same administrator session as other internal admin workspaces;
  - read-only readiness cockpit for rollout decisions.
- Improved browser customer-auth failures:
  - same-origin auth proxy renders a CPGHero-branded controlled-rollout page for HTML navigation
    failures;
  - programmatic callers still receive JSON errors.

## Trust boundaries

- Customer-facing surfaces remain CPGHero-branded.
- WorkOS remains an authentication provider only.
- CPGHero remains the authorization source of truth for account/workspace membership, roles,
  permissions, entitlements, projects, report access, Live API usage controls, and billing.
- The readiness endpoint is internal/admin only and intentionally shows implementation state needed
  for rollout operations.
- The readiness response does not expose WorkOS API keys, cookie passwords, webhook secrets,
  provider subject ids, or raw webhook payloads.

## Explicitly not included

- Does not enable production customer login.
- Does not disable the canary.
- Does not change WorkOS credentials.
- Does not add enterprise SSO, SCIM, or Directory Sync.
- Does not issue customer Live API keys.
- Does not add customer account-administration screens.
- Does not change reports, proximity metrics, collection requests, source-provider calls, PDP calls,
  AI calls, PDFs, or historical artifacts.

## Verification

- `ruff check` passed for the changed Python source and focused tests.
- Focused Python tests passed:
  - `apps/api/tests/test_customer_identity.py`
  - `apps/api/tests/test_customer_provisioning.py`
  - `packages/python/rci-core/tests/test_identity.py`
- Focused web proxy Vitest passed:
  - `apps/web/src/lib/customer-auth-proxy.test.ts`
- Full workspace TypeScript typecheck was not completed locally because the interrupted pnpm
  install left the workspace without normal Vitest type symlinks. CI remains the authoritative full
  web validation gate.

## Next safe rollout step

After this deploy, validate the readiness page in production while customer login remains disabled.
Only after the cockpit confirms expected invitation/webhook state should Railway set:

- `CPGHERO_CUSTOMER_AUTH_PROVIDER=workos`
- `CPGHERO_CUSTOMER_AUTH_CANARY_ENABLED=true`
- `CPGHERO_CUSTOMER_AUTH_ALLOWED_EMAILS=brian@cpghero.com`

That is a canary, not broad cutover. Broad customer login should remain blocked until explicit
approval after the canary login and `/api/v1/me` principal resolution are verified.
