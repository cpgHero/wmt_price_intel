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
});
