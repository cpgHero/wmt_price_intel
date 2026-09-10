import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

describe("canonical report dataset audit script", () => {
  it("is exposed as a root report QA command", () => {
    const packageJson = JSON.parse(
      readFileSync(
        new URL("../../../../package.json", import.meta.url),
        "utf8",
      ),
    ) as { scripts?: Record<string, string> };

    expect(packageJson.scripts?.["reports:audit-canonical"]).toBe(
      "node scripts/audit_canonical_report_dataset.mjs",
    );
  });

  it("resolves schema dependencies from the contracts package before root fallback", () => {
    const source = readFileSync(
      new URL(
        "../../../../scripts/audit_canonical_report_dataset.mjs",
        import.meta.url,
      ),
      "utf8",
    );

    expect(source).toMatch(
      /join\(\s*repositoryRoot,\s*"packages",\s*"typescript",\s*"contracts",\s*"node_modules",\s*\)/,
    );
    expect(source).toContain('join(repositoryRoot, "node_modules")');
    expect(source).toContain("RCI_NODE_MODULES_FALLBACK");
    expect(source).toContain("canonical-report-dataset.schema.json");
    expect(source).toContain("outcome is walmart_wins but price_delta says");
    expect(source).toContain("outcome is competitor_wins but price_delta says");
    expect(source).toContain(
      "price_delta does not reconcile to displayed reporting prices",
    );
  });
});
