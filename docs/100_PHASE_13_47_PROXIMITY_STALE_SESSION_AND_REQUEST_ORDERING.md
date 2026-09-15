# Phase 13.47 — Proximity stale-session and request-ordering stability

Date: 2026-09-14
Status: Local verification complete; production deployment pending

## Verified issue

Live validation on the Railway production host showed that a stale or expired Proximity browser tab could continue displaying previously server-rendered location content while client-side Proximity reloads returned `401` at the web route boundary. In that state, changing retailer or radius could leave the page in a misleading partial view instead of clearly requiring customer sign-in.

The same Proximity workspace also had no latest-request guard. If multiple retailer, country, or radius reloads were in flight, an older response could still apply after a newer request started.

## Implemented change

- Proximity client reloads now detect `401` from `/api/proximity/retailers` and `/api/proximity`.
- On `401`, the page sets an explicit expired-session message and redirects through `/api/auth/login` with the current Proximity path and query preserved as `return_to`.
- Proximity reloads now track a monotonic load sequence and ignore stale success/error/finally updates from older requests once a newer reload starts.
- The customer sign-in return URL builder is tested as a pure helper.

## Boundaries

This change does not grant production roles, broaden account-owner access, change WorkOS credentials, change canary allowlists, alter location rows, coordinates, retailer eligibility, nearest-location Haversine math, proximity metrics, product Search evidence, observed product distribution, matching, report calculations, source-provider calls, PDP calls, AI calls, PDFs, or historical artifacts.

## Verification

- Focused web test run passed with the pinned Node/pnpm runtime:
  - `pnpm --filter @rci/web test -- proximity-workspace.test.ts`
  - 43 test files passed; 247 tests passed.
