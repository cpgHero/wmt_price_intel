import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const publicAvailabilityRoutes = [
  { paths: ["../app/api/price-monitoring/[analysisId]/route.ts"] },
  { paths: ["../app/api/price-monitoring/[analysisId]/catalog/route.ts"] },
  { paths: ["../app/api/price-monitoring/[analysisId]/map/route.ts"] },
  {
    paths: [
      "../app/api/price-monitoring/[analysisId]/architecture-matrix/route.ts",
    ],
  },
  { paths: ["../app/api/price-monitoring/[analysisId]/evidence.csv/route.ts"] },
  {
    paths: [
      "../app/api/analyses/[analysisId]/competitive-decision-quality/route.ts",
    ],
  },
  {
    paths: [
      "../app/api/analyses/[analysisId]/competitive-portfolio-scorecards/route.ts",
    ],
  },
  {
    paths: [
      "../app/api/analyses/[analysisId]/competitive-product-coverage/route.ts",
    ],
  },
  {
    paths: [
      "../app/api/analyses/[analysisId]/competitive-product-leadership/route.ts",
    ],
  },
  {
    paths: [
      "../app/api/analyses/[analysisId]/canonical-report-dataset/route.ts",
      "./canonical-report-dataset-route.ts",
    ],
    minNoStoreMentions: 1,
  },
  {
    paths: [
      "../app/api/analyses/[analysisId]/product-decisions/[decisionId]/evidence/route.ts",
    ],
  },
];

const publicAvailabilityClients = [
  "../app/price-monitoring/[analysisId]/workspace.tsx",
  "../app/price-monitoring/[analysisId]/evidence-retail-map.tsx",
  "../app/price-monitoring/[analysisId]/price-architecture-matrix.tsx",
  "../app/analyses/[analysisId]/workspace.tsx",
  "./competitive-product-leadership-client.ts",
];

describe("public availability proxy caching", () => {
  it.each(publicAvailabilityRoutes)(
    "does not cache successful or quarantined availability responses: $paths",
    ({ paths, minNoStoreMentions = 2 }) => {
      const source = paths
        .map((relativePath) =>
          readFileSync(new URL(relativePath, import.meta.url), "utf8"),
        )
        .join("\n");

      expect(source).toContain("no-store");
      expect(source.match(/no-store/g)?.length ?? 0).toBeGreaterThanOrEqual(
        minNoStoreMentions,
      );
      expect(source).not.toContain("stale-while-revalidate");
    },
  );

  it.each(publicAvailabilityClients)(
    "revalidates client reads and exits stale UI when quarantine begins: %s",
    (relativePath) => {
      const source = readFileSync(
        new URL(relativePath, import.meta.url),
        "utf8",
      );

      expect(source).toContain('cache: "no-store"');
      expect(source).toContain("response.status === 409");
      expect(source).toContain("window.location.reload()");
    },
  );

  it("does not retain analysis payloads in a client-only navigation cache", () => {
    const source = readFileSync(
      new URL(
        "../app/price-monitoring/[analysisId]/workspace.tsx",
        import.meta.url,
      ),
      "utf8",
    );

    expect(source).not.toContain("viewCache");
    expect(source).not.toContain("catalogCache");
  });

  it("revalidates every competitive-analysis drawer request", () => {
    const source = readFileSync(
      new URL("../app/analyses/[analysisId]/workspace.tsx", import.meta.url),
      "utf8",
    );
    const fetchCount = source.match(/fetch\(/g)?.length ?? 0;

    expect(fetchCount).toBeGreaterThan(0);
    expect(source.match(/cache: "no-store"/g)?.length ?? 0).toBe(fetchCount);
    expect(source.match(/response.status === 409/g)?.length ?? 0).toBe(
      fetchCount,
    );
  });

  it("does not cache product-evidence JSON, CSV, or quarantine responses", () => {
    const source = readFileSync(
      new URL(
        "../app/api/analyses/[analysisId]/product-decisions/[decisionId]/evidence/route.ts",
        import.meta.url,
      ),
      "utf8",
    );

    expect(source.match(/private, no-store/g)?.length ?? 0).toBe(3);
  });
});
