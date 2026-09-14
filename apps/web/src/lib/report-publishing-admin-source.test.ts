import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const reportPublishingAdminSource = readFileSync(
  new URL(
    "../app/admin/report-publishing/report-publishing-admin.tsx",
    import.meta.url,
  ),
  "utf8",
);

describe("report publishing admin source contract", () => {
  it("keeps customer report access manageable by account, workspace, and grant state", () => {
    expect(reportPublishingAdminSource).toContain("Access overview");
    expect(reportPublishingAdminSource).toContain("Revoked grants");
    expect(reportPublishingAdminSource).toContain("Accounts");
    expect(reportPublishingAdminSource).toContain("Workspace scopes");
    expect(reportPublishingAdminSource).toContain("Find ready report");
    expect(reportPublishingAdminSource).toContain("Find grants");
    expect(reportPublishingAdminSource).toContain("GrantStatusFilter");
    expect(reportPublishingAdminSource).toContain("aria-pressed={");
  });

  it("keeps grant actions safe and customer-view scoped", () => {
    expect(reportPublishingAdminSource).toContain("Confirm revoke");
    expect(reportPublishingAdminSource).toContain(
      "Soft-revoke this report grant without deleting the audit row.",
    );
    expect(reportPublishingAdminSource).toContain(
      "href={`/customer/reports/${grant.access_id}`}",
    );
    expect(reportPublishingAdminSource).toContain("remain keyed by the grant");
  });
});
