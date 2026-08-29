import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { platformDocGroups, platformDocumentation } from "./platform-docs";

function allText(): string {
  return JSON.stringify(platformDocumentation).toLocaleLowerCase();
}

function repositoryJson<T>(relativePath: string): T {
  return JSON.parse(
    readFileSync(
      new URL(`../../../../${relativePath}`, import.meta.url),
      "utf8",
    ),
  ) as T;
}

describe("platform owner and administrator documentation", () => {
  it("provides a unique maintained guide in every documentation group", () => {
    const ids = platformDocumentation.guides.map((guide) => guide.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(platformDocumentation.version).toMatch(/^\d+\.\d+\.\d+$/);
    expect(platformDocumentation.lastVerified).toBeTruthy();

    for (const group of platformDocGroups) {
      expect(
        platformDocumentation.guides.some((guide) => guide.group === group.id),
      ).toBe(true);
    }
  });

  it("documents the complete authority and certification boundaries", () => {
    const text = allText();
    expect(text).toContain("search data owns store-specific price");
    expect(text).toContain("location master owns");
    expect(text).toContain("pdp");
    expect(text).toContain("retailer packs");
    expect(text).toContain("product packs");
    expect(text).toContain("deterministic code computes");
    expect(text).toContain("matching v2 gold-set replay");
    expect(text).toContain("disables automatic match fallback");
    expect(text).toContain("one identified reviewer approves or rejects once");
    expect(text).toContain("final until someone explicitly flags it");
    expect(text).toContain("kroger product details uses the provider-catalog");
    expect(text).toContain("kroger pdp contract is verified");
    expect(text).toContain("cache-adjusted estimate");
  });

  it("maintains valid tables, internal links, limitations, and change orders", () => {
    const ids = new Set(platformDocumentation.guides.map((guide) => guide.id));
    expect(ids).toContain("data-lifecycle");
    expect(ids).toContain("ai-integration-map");
    expect(ids).toContain("limitations");
    expect(ids).toContain("change-orders");

    for (const guide of platformDocumentation.guides) {
      for (const link of guide.links ?? []) expect(link.href).toMatch(/^\//);
      for (const block of guide.blocks) {
        if (block.kind === "steps") {
          for (const item of block.items) {
            if (item.link) expect(item.link.href).toMatch(/^\//);
          }
        }
        if (block.kind === "table") {
          for (const row of block.rows) {
            expect(row).toHaveLength(block.columns.length);
          }
        }
      }
    }

    const changeOrders = platformDocumentation.guides.find(
      (guide) => guide.id === "change-orders",
    );
    expect(changeOrders).toBeDefined();
    expect(JSON.stringify(changeOrders)).toContain("2026-08-16");
  });

  it("documents every current AI lane and the deterministic authority boundary", () => {
    const guide = platformDocumentation.guides.find(
      (candidate) => candidate.id === "ai-integration-map",
    );
    const text = JSON.stringify(guide).toLocaleLowerCase();

    expect(text).toContain("governed insight drafting");
    expect(text).toContain("governed narrative drafting");
    expect(text).toContain("matching v2 evidence review");
    expect(text).toContain("product-image vision");
    expect(text).toContain("gpt-5.6-sol");
    expect(text).toContain("gpt-5.6-luna");
    expect(text).toContain("store=false");
    expect(text).toContain("openai_model_classification");
    expect(text).toContain("deterministic analytics");
    expect(text).toContain("human decision boundary");
    expect(text).toContain("required maintenance whenever ai changes");
  });

  it("keeps the retailer integration registry synchronized with enabled catalogs", () => {
    const guide = platformDocumentation.guides.find(
      (candidate) => candidate.id === "retailer-integration-registry",
    );
    const text = JSON.stringify(guide).toLocaleLowerCase();
    const searchCatalog = repositoryJson<{
      retailers: Array<{
        credits_per_successful_page: number;
        display_name: string;
        endpoint: string;
        id: string;
        status: string;
      }>;
    }>("config/retailer-catalog.json");
    const pdpCatalog = repositoryJson<{
      endpoints: Array<{
        credits_per_successful_page: number;
        path: string;
        retailer_id: string;
      }>;
    }>("config/product-detail-catalog.json");
    const overrides = repositoryJson<{
      overrides: Array<{
        retailer_id: string;
        runtime_path: string;
      }>;
    }>("config/metricscart-endpoint-overrides.json");
    const runtimeOverrides = new Map(
      overrides.overrides.map((entry) => [
        entry.retailer_id,
        entry.runtime_path,
      ]),
    );
    const pdpByRetailer = new Map(
      pdpCatalog.endpoints.map((entry) => [entry.retailer_id, entry]),
    );
    const searchTable = guide?.blocks.find(
      (block) =>
        block.kind === "table" &&
        block.title === "Enabled Search-by-ZIP adapters",
    );
    const pdpTable = guide?.blocks.find(
      (block) =>
        block.kind === "table" &&
        block.title === "PDP enrichment registry for enabled Search retailers",
    );
    expect(searchTable?.kind).toBe("table");
    expect(pdpTable?.kind).toBe("table");

    for (const retailer of searchCatalog.retailers.filter(
      (entry) => entry.status === "enabled",
    )) {
      const pdp = pdpByRetailer.get(retailer.id);
      expect(pdp).toBeDefined();
      if (searchTable?.kind === "table") {
        expect(searchTable.rows).toContainEqual(
          expect.arrayContaining([
            retailer.id,
            retailer.endpoint,
            String(retailer.credits_per_successful_page),
          ]),
        );
      }
      if (pdpTable?.kind === "table") {
        expect(pdpTable.rows).toContainEqual(
          expect.arrayContaining([
            retailer.display_name,
            runtimeOverrides.get(retailer.id) ?? pdp?.path ?? "",
            String(pdp?.credits_per_successful_page),
          ]),
        );
      }
    }

    expect(text).toContain("enabled is not the same as universally callable");
    expect(text).toContain("run-specific retailer preflight");
    expect(text).toContain("positive-price search location");
    expect(text).toContain("30-day policy");
    expect(text).toContain("known third party");
    expect(text).toContain("missing seller");
  });

  it("documents source-to-metric authority, grain, and audit lineage", () => {
    const guide = platformDocumentation.guides.find(
      (candidate) => candidate.id === "source-metric-lineage",
    );
    const text = JSON.stringify(guide).toLocaleLowerCase();

    expect(text).toContain("immutable metricscart search response");
    expect(text).toContain("frozen location-master snapshot");
    expect(text).toContain("fresh retained pdp evidence");
    expect(text).toContain("pinned product pack");
    expect(text).toContain("retailer pack");
    expect(text).toContain("multiple products at one store count once");
    expect(text).toContain("physical competitors count distinct stores");
    expect(text).toContain(
      "service-area retailers count distinct delivery zips",
    );
    expect(text).toContain("selected 1, 3, or 5 miles");
    expect(text).toContain("not proof of out-of-stock or non-carriage");
    expect(text).toContain(
      "ai does not calculate or repair authoritative values",
    );
  });
});
