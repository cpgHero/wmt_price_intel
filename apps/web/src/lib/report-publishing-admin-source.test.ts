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
  it("keeps customer report access disabled during the legacy restore", () => {
    expect(reportPublishingAdminSource).toContain(
      "const CUSTOMER_REPORT_ACCESS_ENABLED = false",
    );
    expect(reportPublishingAdminSource).toContain(
      "CUSTOMER_REPORT_ACCESS_ENABLED ?",
    );
    expect(reportPublishingAdminSource).not.toContain(
      "Promise.all([loadJobs(), loadCustomerAccess()])",
    );
  });

  it("keeps dormant grant actions safe and customer-view scoped", () => {
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
