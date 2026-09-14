# Phase 14.11 — Customer workspace shell

## Objective

Add a customer-facing landing surface for the WorkOS canary without broadening access beyond the
approved canary users and without pretending existing report routes are fully tenant-enforced.

The canary proved that invitations, signed identity webhooks, and CPGHero membership activation can
work end to end. The next safe product step is to give authenticated customer users a clear place to
land where CPGHero shows the exact principal state it resolved: user email, account, workspace,
roles, permissions, and entitlements.

## Implemented

- Added `/customer` as a dynamic customer workspace route.
- Added `My Workspace` to the application navigation.
- Added a top-bar customer session control:
  - anonymous users see a CPGHero sign-in action;
  - authenticated users see their email, primary role, a link to `/customer`, and sign-out.
- Added a customer workspace page backed by `/api/auth/me`:
  - shows the resolved CPGHero account and workspace identifiers;
  - shows roles, permissions, and entitlement count;
  - clearly states when no paid product entitlements are configured for the canary account.

## Trust boundaries

- Customer-visible copy remains CPGHero branded.
- The page consumes the CPGHero principal endpoint and does not expose provider subject IDs,
  credentials, webhook details, or raw identity payloads.
- This shell does not grant data access by itself. It displays the principal that future
  tenant-scoped analytics, project, export, and billing routes must enforce.

## Explicitly not included

- Does not broaden the customer-auth canary allowlist.
- Does not disable the canary.
- Does not create customer API keys.
- Does not add billing, usage, or account-administration workflows.
- Does not enforce account/workspace scope on every existing report or collection route.
- Does not change reports, proximity metrics, collection requests, source-provider calls, PDP calls,
  AI calls, PDFs, or historical artifacts.

## Verification

- Focused Prettier check passed for touched web files.
- `pnpm --filter @rci/web exec tsc --noEmit` passed.
- Focused navigation Vitest passed:
  - `apps/web/src/lib/app-navigation.test.ts`
- `pnpm --filter @rci/web lint` passed.
- `pnpm --filter @rci/web build` passed and includes `/customer` in the route output.
- Platform Docs coverage gate passed.

## Next safe rollout step

Implement tenant enforcement seams before broad access:

1. define which report, collection, proximity, and export routes are customer-accessible;
2. require the resolved CPGHero customer principal on those routes;
3. filter records by account/workspace/project ownership;
4. add owner/admin diagnostics that compare customer-visible counts with system totals;
5. only then expand beyond canary users.
