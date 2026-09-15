import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const customerPageSource = readFileSync(
  new URL("../app/customer/page.tsx", import.meta.url),
  "utf8",
);
const customerReportPageSource = readFileSync(
  new URL("../app/customer/reports/[accessId]/page.tsx", import.meta.url),
  "utf8",
);
const customerReportApiSource = readFileSync(
  new URL(
    "../app/api/customer/reports/[accessId]/report/route.ts",
    import.meta.url,
  ),
  "utf8",
);

describe("customer report workspace source contract", () => {
  it("redirects dormant customer workspace pages in legacy restore mode", () => {
    expect(customerPageSource).toContain('redirect("/")');
    expect(customerReportPageSource).toContain('redirect("/analyses")');
  });

  it("keeps customer report APIs disabled instead of proxying report grants", () => {
    expect(customerReportApiSource).toContain(
      "customerReportApiDisabledResponse",
    );
    expect(customerReportApiSource).not.toContain("loadServerConfig");
    expect(customerReportApiSource).not.toContain("fetch(");
  });
});
