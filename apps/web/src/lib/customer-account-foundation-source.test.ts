import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const customerAuthAdminSource = readFileSync(
  new URL(
    "../app/admin/customer-auth/customer-auth-admin.tsx",
    import.meta.url,
  ),
  "utf8",
);
const accountFoundationProxySource = readFileSync(
  new URL(
    "../app/api/admin/customer-auth/account-foundation/route.ts",
    import.meta.url,
  ),
  "utf8",
);
const customerAuthPageSource = readFileSync(
  new URL("../app/admin/customer-auth/page.tsx", import.meta.url),
  "utf8",
);

describe("customer account foundation admin source contract", () => {
  it("keeps the account foundation read-only and scoped to core access primitives", () => {
    expect(customerAuthAdminSource).toContain("Account access foundation");
    expect(customerAuthAdminSource).toContain(
      "Read-only CPGHero source-of-truth",
    );
    expect(customerAuthAdminSource).toContain("Customer accounts");
    expect(customerAuthAdminSource).toContain("Customer accounts only");
    expect(customerAuthAdminSource).toContain("Account detail");
    expect(customerAuthAdminSource).toContain("Workspace scopes");
    expect(customerAuthAdminSource).toContain("Members");
    expect(customerAuthAdminSource).toContain("Entitlements");
    expect(customerAuthAdminSource).toContain("Active report grants");
    expect(customerAuthAdminSource).toContain("Reset view");
    expect(customerAuthAdminSource).toContain("Login readiness");
    expect(customerAuthAdminSource).toContain("Open detail drawer");
    expect(customerAuthAdminSource).toContain("Workspace & report access");
    expect(customerAuthAdminSource).toContain(
      "Login, invitation, and identity state",
    );
    expect(customerAuthAdminSource).toContain("Read-only guardrail");
  });

  it("surfaces identity binding without exposing upstream provider identifiers", () => {
    expect(customerAuthAdminSource).toContain(
      "has_identity_provider_user_binding",
    );
    expect(customerAuthAdminSource).toContain(
      "has_identity_provider_organization_binding",
    );
    expect(customerAuthAdminSource).not.toContain("workos_user_id");
    expect(customerAuthAdminSource).not.toContain("workos_organization_id");
    expect(customerAuthAdminSource).not.toContain("Internal provider:");
    expect(customerAuthPageSource).toContain('redirect("/admin/operations")');
    expect(customerAuthPageSource).not.toContain("WorkOS webhook");
  });

  it("keeps the account foundation proxy behind the administrator session and internal API", () => {
    expect(accountFoundationProxySource).toContain(
      "verifyAdminAccess(request)",
    );
    expect(accountFoundationProxySource).toContain(
      "/api/v1/admin/customer-provisioning/account-foundation",
    );
    expect(accountFoundationProxySource).toContain("X-RCI-Admin-Token");
    expect(accountFoundationProxySource).toContain("private, no-store");
  });
});
