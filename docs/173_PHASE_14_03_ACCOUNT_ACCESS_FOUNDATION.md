# Phase 14.03 — Account, workspace, role, and entitlement foundation

## Purpose

This phase adds the first durable CPGHero account-access foundation without committing to a final customer login or SSO provider.

The goal is to make tenant/account/security work concrete and testable while avoiding risky assumptions about identity-provider selection.

## Scope

Implemented in this phase:

- additive database migration for accounts, workspaces, memberships, roles, permissions, entitlements, and audit-event account/workspace fields;
- seed account/workspace records for the existing standalone organization so current data has a migration bridge;
- seeded role and permission vocabulary aligned to the approved CPGHero platform vision;
- shared Python access-control primitives for permission and entitlement checks;
- unit tests for permission expansion, entitlement enforcement, and system-role classification;
- Platform Docs update and change-order entry.

Not implemented in this phase:

- customer login UI;
- identity provider integration;
- SSO;
- password reset or invitation flows;
- customer API keys;
- row-level route enforcement;
- support impersonation;
- account billing UI;
- production data migration beyond the compatibility seed.

## Why this is additive

The existing system already has `organization` and `app_user` tables used by collection, analysis, reporting, and governance tables. Renaming those tables directly would be risky because many historical migrations and foreign keys depend on them.

This phase therefore adds the CPGHero model beside the current tables:

- `organization` remains the compatibility tenant root;
- `account` maps one-to-one to `organization` for now;
- `workspace` sits under `account`;
- `app_user` remains the user identity record until the final login provider is selected;
- memberships, roles, permissions, and entitlements bind users to accounts/workspaces without rewriting existing evidence tables.

This gives future phases a real account boundary while preserving current production behavior.

## Database model added

| Table | Purpose |
| --- | --- |
| `account` | CPGHero customer/internal/system account mapped to an existing organization. |
| `workspace` | Optional subdivision under an account for teams, clients, brands, or business units. |
| `platform_permission` | Governed permission vocabulary. |
| `platform_role` | System-managed or account-scoped role definitions. |
| `platform_role_permission` | Many-to-many role-to-permission assignment. |
| `account_membership` | User membership in an account. |
| `account_membership_role` | Role assignments at account membership level. |
| `workspace_membership` | User membership in a workspace through an account membership. |
| `workspace_membership_role` | Role assignments at workspace membership level. |
| `account_entitlement` | Commercial feature/limit entitlements for an account. |
| `audit_event` additions | Optional account/workspace/request/network-hash fields for future account-scoped audit. |

The migration seeds:

- a `CPGHero System` account for the existing standalone organization;
- a default workspace;
- baseline customer and system permissions;
- baseline system, account, workspace, project, developer, and billing roles;
- role-permission assignments.

## Permission vocabulary

Initial permission keys:

- `users.manage`
- `roles.manage`
- `api_keys.manage`
- `projects.create`
- `projects.manage`
- `projects.approve_paid_run`
- `exports.download`
- `analytics.view`
- `analytics.share`
- `billing.view`
- `system.admin`
- `system.provider_admin`
- `system.governance`

System permissions are not customer-visible.

## Role vocabulary

Initial roles:

| Role key | Scope | Intent |
| --- | --- | --- |
| `system_owner` | System | Full platform owner access. |
| `system_admin` | System | Platform operations and support access. |
| `system_analyst` | System | Internal analytics/governance support. |
| `account_owner` | Account | Owns account settings, users, usage, and all projects. |
| `account_admin` | Account | Manages users, projects, and delivery settings. |
| `project_owner` | Project | Creates and manages assigned projects. |
| `analyst` | Workspace | Explores analytics and downloads permitted evidence. |
| `viewer` | Workspace | Views permitted reports and dashboards. |
| `developer` | Account | Uses developer docs, API keys, and integration diagnostics. |
| `billing_user` | Account | Views usage and billing exports. |

## Entitlement vocabulary

Initial entitlement keys in shared code:

- `live_api`
- `bulk_projects`
- `app_analytics`
- `endpoint.search`
- `endpoint.product_detail`
- `endpoint.reviews`
- `analytics.price_intelligence`
- `analytics.competitive_intelligence`
- `analytics.share_of_search`
- `analytics.review_radar`
- `analytics.proximity`
- `delivery.app_download`
- `delivery.email`
- `delivery.sftp`
- `delivery.s3`
- `delivery.azure_blob`

Entitlements are account-level commercial controls. Permissions say what a user may do; entitlements say what an account has purchased or enabled.

## Shared code model

`rci_core.access_control` adds:

- typed permission, entitlement, and role vocabularies;
- `ROLE_PERMISSIONS`;
- `ROLE_SCOPES`;
- `AccessPrincipal`;
- `has_permission`, `require_permission`, `has_entitlement`, and `require_entitlement` helpers;
- system-actor classification.

This is intentionally identity-provider-agnostic. A future auth integration should resolve the login/session/API key into an `AccessPrincipal`, then route dependencies can enforce permissions and entitlements.

## Security interpretation

This phase is a foundation, not a complete security rollout.

What is now safer:

- the target account/workspace/RBAC/entitlement model exists in schema and code;
- future work has a stable vocabulary for checks instead of inventing per-route strings;
- audit events can now carry account/workspace/request/network-hash context.

What remains unsafe for customer launch:

- routes do not yet enforce the new account model;
- current admin sessions still exist;
- customer login has not been selected or implemented;
- existing queries still need route-by-route tenant scoping tests;
- API keys and account usage ledger are still future phases.

## Acceptance criteria

Local acceptance:

- migration upgrades and downgrades cleanly;
- shared access-control tests pass;
- masking gate passes;
- Platform Docs coverage gate passes;
- formatting and lint checks pass for changed files.

CI acceptance:

- documentation, Python, TypeScript, and container jobs pass.

## Next recommended phase

Phase 14.04 should add principal resolution and route-level enforcement in a narrow vertical slice:

1. resolve a system/admin principal from current admin session for internal routes;
2. resolve a customer principal from a temporary trusted header only in non-production test mode, or from the chosen auth provider if selected;
3. add account/workspace scope dependencies in FastAPI;
4. add route tests proving cross-account denial;
5. keep UI customer account pages behind the working principal model.

Before production customer login, the owner still needs to choose the identity approach.

