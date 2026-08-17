import { describe, expect, it } from "vitest";

import { platformDocGroups, platformDocumentation } from "./platform-docs";

function allText(): string {
  return JSON.stringify(platformDocumentation).toLocaleLowerCase();
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
});
