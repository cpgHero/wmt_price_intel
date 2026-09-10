import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const workspaceSource = readFileSync(
  new URL(
    "../app/analyses/[analysisId]/canonical-report-workspace.tsx",
    import.meta.url,
  ),
  "utf8",
);

const stylesSource = readFileSync(
  new URL("../app/styles.css", import.meta.url),
  "utf8",
);

describe("canonical report workspace source contract", () => {
  it("keeps the app report organized around the five app-first tabs", () => {
    expect(workspaceSource).toContain("Executive Summary");
    expect(workspaceSource).toContain("Product Wins & Losses");
    expect(workspaceSource).toContain("Distribution & Assortment");
    expect(workspaceSource).toContain("Price Architecture");
    expect(workspaceSource).toContain("Evidence & QA");
  });

  it("keeps the product action board focused on all governed relationships", () => {
    expect(workspaceSource).toContain("Product action board");
    expect(workspaceSource).toContain("All Walmart losses");
    expect(workspaceSource).toContain("All Walmart wins");
    expect(workspaceSource).toContain("These are all included");
    expect(workspaceSource).toContain("Search products");
    expect(workspaceSource).toContain("Walmart brand type");
    expect(workspaceSource).toContain("Walmart footprint");
    expect(workspaceSource).toContain("Action priority");
  });

  it("labels percent-gap sorting and displayed-basis price deltas plainly", () => {
    expect(workspaceSource).toContain("Largest percent gap");
    expect(workspaceSource).toContain(
      "Walmart reporting price is ${deltaLabel} on the displayed basis.",
    );
    expect(stylesSource).toContain(".canonical-product-card-footer small");
  });

  it("keeps private-label, national, regional, and unclassified review factual", () => {
    expect(workspaceSource).toContain("summarizeCanonicalBrandTypes");
    expect(workspaceSource).toContain("Brand role focus");
    expect(workspaceSource).toContain(
      "Counts below are factual summaries of included governed product",
    );
    expect(workspaceSource).toContain(
      "Regional brand content remains fact-only.",
    );
    expect(workspaceSource).toContain("broad-footprint");
    expect(stylesSource).toContain(".canonical-brand-role-grid");
  });

  it("keeps Executive Summary, Distribution, and Price Architecture distinct from the card board", () => {
    expect(workspaceSource).toContain("Complete Walmart loss action list");
    expect(workspaceSource).toContain("Complete Walmart win action list");
    expect(workspaceSource).toContain("ExecutivePriorityTable");
    expect(workspaceSource).toContain("Product footprint table");
    expect(workspaceSource).toContain("ProductFootprintTable");
    expect(workspaceSource).toContain("Price ladder");
    expect(workspaceSource).toContain("PriceArchitectureTable");
    expect(workspaceSource).not.toContain("Product footprint cards");
    expect(workspaceSource).not.toContain(
      "Top Walmart wins by product footprint",
    );
    expect(workspaceSource).not.toContain("slice(0, 8)");
    expect(workspaceSource).not.toContain("slice(0, 25)");
    expect(stylesSource).toContain(".canonical-insight-table");
  });

  it("connects distribution to exact product location evidence instead of stock claims", () => {
    const compact = workspaceSource.replace(/\s+/g, " ");

    expect(workspaceSource).toContain("Exact-product map");
    expect(workspaceSource).toContain("ProductLocationEvidencePanel");
    expect(workspaceSource).toContain("ExactProductMap");
    expect(workspaceSource).toContain("MappedLocationTable");
    expect(workspaceSource).toContain("Mapped preview");
    expect(workspaceSource).toContain("Store list drawer");
    expect(workspaceSource).toContain("StoreEvidenceDrawer");
    expect(workspaceSource).toContain("/api/price-monitoring/");
    expect(workspaceSource).toContain('target.product, "full"');
    expect(workspaceSource).toContain("Download evidence CSV");
    expect(workspaceSource).toContain("Excel");
    expect(workspaceSource).toContain("JSON");
    expect(workspaceSource).toContain("searchedStoreCountFromMap");
    expect(workspaceSource).toContain("searchedStoreRows");
    expect(workspaceSource).toContain("not_observed_searched_store_count");
    expect(workspaceSource).toContain("observed_distribution_store_count");
    expect(workspaceSource).toContain("store share");
    expect(workspaceSource).toContain("distribution_store_count");
    expect(workspaceSource).toContain("service_area_presence_count");
    expect(workspaceSource).toContain("searched_store_count");
    expect(workspaceSource).toContain("distributionShareLabel");
    expect(compact).toContain("not inventory or in-stock status");
    expect(compact).toContain(
      "This is distribution evidence, not an in-stock claim.",
    );
    expect(stylesSource).toContain(".canonical-map-card");
    expect(stylesSource).toContain(".canonical-map-point-layer");
    expect(stylesSource).toContain(".canonical-store-drawer");
    expect(stylesSource).toContain(".canonical-drawer-export-actions");
  });

  it("keeps trust language visible in the hidden preview", () => {
    const lower = workspaceSource
      .toLocaleLowerCase("en-US")
      .replace(/\s+/g, " ");

    expect(workspaceSource).toContain("No inventory claims");
    expect(workspaceSource).toContain("Zero prices treated as missing");
    expect(workspaceSource).toContain("Seller governed");
    expect(workspaceSource).toContain("Evidence through");
    expect(workspaceSource).toContain("Legacy workspace");
    expect(workspaceSource).toContain("price greater than zero");
    expect(workspaceSource).toContain("not an in-stock indicator");
    expect(lower).toContain("service-area presence");
    expect(lower).toContain("is never displayed as a store count");
  });

  it("keeps image-first relationship cards as the primary product presentation", () => {
    expect(workspaceSource).toContain("canonical-product-grid");
    expect(workspaceSource).toContain("RelationshipCard");
    expect(workspaceSource).toContain("ProductTile");
    expect(workspaceSource).toContain("canonical-product-image");
    expect(workspaceSource).toContain('loading="lazy"');
    expect(stylesSource).toContain(".canonical-product-grid");
    expect(stylesSource).toContain("grid-template-columns: 86px 1fr");
  });

  it("keeps Evidence & QA as an explicit checklist instead of scattered counts only", () => {
    expect(workspaceSource).toContain("canonicalReportChecklist");
    expect(workspaceSource).toContain("canonicalReportIntegrityIssues");
    expect(workspaceSource).toContain("Validation checklist");
    expect(workspaceSource).toContain("Dataset integrity");
    expect(workspaceSource).toContain("before export or publication");
    expect(stylesSource).toContain(".canonical-checklist");
    expect(stylesSource).toContain("article.warning");
    expect(stylesSource).toContain("article.blocked");
  });

  it("does not reintroduce report-version commentary into the canonical report copy", () => {
    const lower = workspaceSource.toLocaleLowerCase("en-US");

    expect(lower).not.toContain("previous version");
    expect(lower).not.toContain("prior version");
    expect(lower).not.toContain("changes versus");
    expect(lower).not.toContain("changed from");
    expect(lower).not.toContain("preview only");
    expect(lower).not.toContain("simplified report preview");
  });
});
