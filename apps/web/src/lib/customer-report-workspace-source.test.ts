import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const customerWorkspaceSource = readFileSync(
  new URL("../app/customer/customer-workspace.tsx", import.meta.url),
  "utf8",
);

const customerReportDetailSource = readFileSync(
  new URL(
    "../app/customer/reports/[accessId]/report-detail.tsx",
    import.meta.url,
  ),
  "utf8",
);

describe("customer report workspace source contract", () => {
  it("keeps granted report list labels customer-facing with hidden audit detail", () => {
    expect(customerWorkspaceSource).toContain("Granted reports");
    expect(customerWorkspaceSource).toContain("Ready to open");
    expect(customerWorkspaceSource).toContain("Trust boundary");
    expect(customerWorkspaceSource).toContain("Grant-gated");
    expect(customerWorkspaceSource).toContain(
      "Only reports explicitly granted",
    );
    expect(customerWorkspaceSource).toContain("<details");
    expect(customerWorkspaceSource).toContain("<dt>Analysis</dt>");
    expect(customerWorkspaceSource).toContain("<dt>Result</dt>");
    expect(customerWorkspaceSource).toContain("<dt>Checksum</dt>");
  });

  it("renders the full canonical report through a customer access grant", () => {
    expect(customerReportDetailSource).toContain("CanonicalReportWorkspace");
    expect(customerReportDetailSource).toContain("customerAccessId={accessId}");
    expect(customerReportDetailSource).toContain(
      "/api/customer/reports/${encodeURIComponent(accessId)}/report",
    );
    expect(customerReportDetailSource).toContain(
      "Customer report access summary",
    );
    expect(customerReportDetailSource).toContain("Audit identifiers");
    expect(customerReportDetailSource).toContain(
      "Report data, evidence, and downloads use this access grant.",
    );
  });
});
