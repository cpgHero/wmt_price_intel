# Phase 14.26 — Public Landing and Customer Auth Recovery

Date: 2026-09-14

Status: Local verification complete; PR verification pending.

## Summary

The root route now serves a public CPGHero landing page instead of immediately starting customer login or presenting the signed-in operational dashboard shell. Protected app workspaces remain behind route authentication.

Customer authentication also gains a recovery path for callbacks that reach CPGHero without the temporary login-flow cookie. Those callbacks cannot safely complete the PKCE exchange, so the API restarts customer login instead of returning a terminal controlled-rollout 401 page.

## Operational effect

- `/` is public and explains CPGHero with sign-in entry points.
- In-app brand and Home navigation target `/customer`, the protected customer workspace.
- Protected app, analytics, report, collection, administrator, and same-origin API routes remain gated.
- Production login-flow cookies use callback-compatible attributes for hosted-auth redirects.
- Missing login-flow callbacks restart login at `/api/auth/login?return_to=/customer&auth_restart=missing_flow`.

## Compatibility and boundaries

This change affects public entry and login recovery behavior only. It does not change WorkOS credentials, customer provisioning, roles, entitlements, report calculations, proximity metrics, collection requests, source-provider calls, PDP calls, AI calls, PDFs, or historical artifacts.

## Verification

- Python customer-auth tests for login flow-cookie attributes and missing-flow callback recovery.
- Web route-policy and navigation tests for public `/` and protected `/customer`.
- Web lint, typecheck, build, and local production smoke.
- Documentation coverage and formatting gates.
