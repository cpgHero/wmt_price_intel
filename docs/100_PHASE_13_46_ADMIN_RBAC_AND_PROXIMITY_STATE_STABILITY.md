# Phase 13.46 — Admin RBAC and Proximity State Stability

## Outcome

Administration route checks now recognize the CPGHero customer principal model instead of relying only on the temporary legacy admin-password session. A WorkOS-authenticated CPGHero principal must resolve to the `system.admin` permission before internal Administration pages and web admin API proxies open. Existing legacy admin sessions continue to work as a fallback.

The Proximity page now preserves the selected retailer while the radius is changed, including immediately after a retailer change. Radius-only changes no longer reset unrelated search, relation, sort, saved, state, or detail filters.

## Access-control boundary

- `account_owner` alone does not grant internal Administration access.
- `system_owner` and `system_admin` resolve to `system.admin` and can satisfy the Administration boundary.
- This phase changes code only. It does not grant a production role to any user.
- The admin web proxies still inject the server-side internal admin token only after the web session boundary passes.

## Verification

- `pnpm --filter @rci/web test -- admin-access.test.ts proximity-workspace.test.ts proxy.test.ts route-access-policy.test.ts customer-account-foundation-source.test.ts`
- `pnpm --filter @rci/web typecheck`
- `pnpm --filter @rci/web lint`
- `pnpm --filter @rci/web build`

## Non-goals

This phase does not change WorkOS credentials, canary allowlists, customer provisioning, report calculations, proximity metrics, source-provider calls, PDP calls, AI calls, PDF/report artifacts, or historical evidence.
