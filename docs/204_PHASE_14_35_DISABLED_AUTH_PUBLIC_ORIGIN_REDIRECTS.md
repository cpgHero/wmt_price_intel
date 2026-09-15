# Phase 14.35 — Disabled auth public-origin redirects

## Purpose

Correct the disabled customer-auth routes after production verification showed
that they returned the right status but used Railway's internal service origin
in their `Location` headers.

## Finding

After the legacy reporting and customer-auth rollback deployed, production HTTP
probes showed:

```text
/api/auth/login    307 https://0.0.0.0:3000/
/api/auth/callback 307 https://0.0.0.0:3000/
/api/auth/logout   307 https://0.0.0.0:3000/
```

The rollback handlers were using `new URL(request.url)`. Behind Railway, that
can expose the internal container host instead of the browser-facing public
domain.

## What changed

- A shared `publicRequestOrigin(request)` helper now prefers
  `x-forwarded-host` and `x-forwarded-proto` when present.
- `/api/auth/login`, `/api/auth/callback`, and `/api/auth/logout` redirect to
  `/` on the resolved public app origin.
- Unit coverage now protects the Railway forwarded-origin case for login,
  callback, logout, and the shared origin helper.

## Deliberate non-goals

This fix preserves legacy restore mode. It does not re-enable WorkOS customer
login, customer report APIs, route-cache validation, customer account menus,
canonical report routing, Proximity auth gating, report calculations, database
cleanup, Railway secret changes, source-provider calls, PDP calls, AI calls,
PDF generation, or historical artifact changes.
