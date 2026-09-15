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
    expect(platformDocumentation.version).toBe("1.3.170");
    expect(platformDocumentation.lastVerified).toBeTruthy();

    for (const group of platformDocGroups) {
      expect(
        platformDocumentation.guides.some((guide) => guide.group === group.id),
      ).toBe(true);
    }
  });

  it("documents the complete authority and certification boundaries", () => {
    const text = allText();
    expect(text).toContain("search data owns listed price");
    expect(text).toContain(
      "observed store distribution counts a distinct store when the exact product appears",
    );
    expect(text).toContain("does not use stock status");
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
    expect(text).toContain("deduplicate by retailer product id × store id");
    expect(text).toContain("no count is extrapolated to unobserved locations");
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
    expect(text).toContain("successful-sample quorum");
    expect(text).toContain("retry-exhausted zero-credit");
    expect(text).toContain("remains in the complete frozen collection");
    expect(text).toContain("hard and billable non-404 failures remain fatal");
    expect(text).toContain("canonical eight-digit store");
    expect(text).toContain("eligibility policy reconciliation");
    expect(text).toContain("rejects a stale snapshot");
    expect(text).toContain("reviewed-plan");
    expect(text).toContain("whole-operation lock");
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

  it("documents production incident, recovery, and release governance", () => {
    const incident = platformDocumentation.guides.find(
      (candidate) => candidate.id === "incident-response-recovery",
    );
    const release = platformDocumentation.guides.find(
      (candidate) => candidate.id === "release-manifest-change-control",
    );
    const text = JSON.stringify({ incident, release }).toLocaleLowerCase();

    expect(platformDocumentation.version).toBe("1.3.170");
    expect(platformDocumentation.guides).toHaveLength(22);
    expect(text).toContain("protect evidence before restoring speed");
    expect(text).toContain("isolated non-production environment");
    expect(text).toContain("operator-attested");
    expect(text).toContain(
      "daily and weekly railway volume backup schedules are active",
    );
    expect(text).toContain("pitr was enabled");
    expect(text).toContain("forced wal segment archived successfully");
    expect(text).toContain("migration mismatch");
    expect(text).toContain("zero-credit canary");
    expect(text).toContain("separate, immutable run");
    expect(allText()).toContain("five current replicas");
    expect(allText()).toContain("migration 0049");
    expect(allText()).toContain(
      "migration 0052 and its administrator continuation api are authoritative production behavior",
    );
    expect(allText()).toContain("migration 0053 alone remains staged");
    expect(allText()).toContain(
      "landing-page readiness now distinguishes durable publication authority from source-quality disclosures",
    );
    expect(allText()).toContain("8d6c4756-c44f-487e-9a6a-393dc1661b96");
  });

  it("documents paused WorkOS authentication without handing authorization to WorkOS", () => {
    const guides = Object.fromEntries(
      platformDocumentation.guides.map((guide) => [
        guide.id,
        JSON.stringify(guide).toLocaleLowerCase(),
      ]),
    );

    expect(guides["trust-governance"]).toContain("workos authkit");
    expect(guides["trust-governance"]).toContain(
      "cpghero remains the authorization source of truth",
    );
    expect(guides["trust-governance"]).toContain(
      "account/workspace membership",
    );
    expect(guides["trust-governance"]).toContain("migration 0055");
    expect(guides["trust-governance"]).toContain("migration 0056");
    expect(guides["trust-governance"]).toContain(
      "signed workos webhook receiver",
    );
    expect(guides["trust-governance"]).toContain(
      "enterprise sso, directory sync, and scim are not part of the initial rollout",
    );
    expect(guides["trust-governance"]).toContain(
      "railway stores workos variables",
    );
    expect(guides["trust-governance"]).toContain(
      "production web rollout is paused",
    );
    expect(guides["trust-governance"]).toContain(
      "web login, callback, and logout routes redirect to the legacy root",
    );
    expect(guides["trust-governance"]).toContain(
      "/api/auth/me returns private no-store json 401",
    );
    expect(guides["trust-governance"]).toContain(
      "/api/customer/reports routes return a private no-store disabled response without proxying",
    );
    expect(guides["trust-governance"]).toContain(
      "no longer forwards raw webhook payloads",
    );
    expect(guides["trust-governance"]).toContain(
      "non-production customer-principal harness",
    );
    expect(guides["trust-governance"]).toContain(
      "production customer-login web flow is disabled",
    );
    expect(guides["trust-governance"]).toContain(
      "legacy restore mode disables the next.js route-boundary auth gate",
    );
    expect(guides["trust-governance"]).toContain(
      "proxy performs no customer or administrator authentication validation",
    );
    expect(guides["trust-governance"]).toContain(
      "hard-redirects dormant customer pages to legacy app destinations",
    );
    expect(guides["trust-governance"]).toContain(
      "root route is the legacy app home/dashboard",
    );
    expect(guides["trust-governance"]).toContain(
      "legacy administrator password session",
    );
    expect(guides["trust-governance"]).toContain(
      "production must still not configure cpghero_web_route_auth_test_bypass_token",
    );
    expect(guides["change-orders"]).toContain(
      "workos authkit selected and identity mapping foundation added",
    );
    expect(guides["change-orders"]).toContain(
      "anonymous page-shell rendering blocked for protected app routes",
    );
    expect(guides["change-orders"]).toContain(
      "customer route-session validation cache added",
    );
    expect(guides["change-orders"]).toContain(
      "public landing page and customer login recovery added",
    );
    expect(guides["change-orders"]).toContain(
      "customer-principal harness and workos/railway prep added",
    );
    expect(guides["change-orders"]).toContain(
      "workos authkit session bridge added behind disabled production flag",
    );
    expect(guides["change-orders"]).toContain(
      "customer auth provisioning and identity webhook audit foundation added",
    );
    expect(guides["change-orders"]).toContain(
      "customer-visible /api/v1/me response remains cpghero-facing",
    );
    expect(guides["change-orders"]).toContain(
      "identity rollback and legacy report restore prepared",
    );
    expect(guides["change-orders"]).toContain(
      "the next.js proxy performs no customer or administrator authentication validation",
    );
    expect(guides["change-orders"]).toContain(
      "proxy hard-redirects dormant customer pages to legacy app destinations",
    );
    expect(guides["change-orders"]).toContain(
      "/api/customer/reports routes return a private no-store disabled response without proxying",
    );
    expect(guides["change-orders"]).toContain(
      "renders the legacy blueprint competitive intelligence workspace",
    );
    expect(guides["change-orders"]).toContain("proximity remains active");
  });

  it("documents positive-price store distribution without inventory claims", () => {
    const guides = Object.fromEntries(
      platformDocumentation.guides.map((guide) => [
        guide.id,
        JSON.stringify(guide).toLocaleLowerCase(),
      ]),
    );

    expect(guides["analytics-reporting"]).toContain(
      "observed store distribution counts each distinct store once",
    );
    expect(guides["analytics-reporting"]).toContain(
      "does not use store-level stock status",
    );
    expect(guides["analytics-reporting"]).toContain(
      "service-area presence is calculated and labeled separately",
    );
    expect(guides["analytics-reporting"]).toContain(
      "active analysis route renders the legacy blueprint competitive intelligence report workspace",
    );
    expect(guides["analytics-reporting"]).toContain(
      "canonical product-report workspace and simplified navigation are paused",
    );
    expect(guides["analytics-reporting"]).toContain(
      "explicit map-evidence availability",
    );
    expect(guides["analytics-reporting"]).toContain(
      "never extrapolates to unobserved stores",
    );
    expect(guides["source-metric-lineage"]).toContain(
      "observed store distribution",
    );
    expect(guides["source-metric-lineage"]).toContain(
      "distinct stores where the exact retailer product id appears in a store-level search result with price > 0",
    );
    expect(guides["source-metric-lineage"]).toContain(
      "reported separately and never presented as a store count",
    );
    expect(guides["source-metric-lineage"]).toContain(
      "matched positive store-level search prices",
    );
    expect(guides["metric-dictionary"]).toContain(
      "it is not inventory or in-stock status",
    );
    expect(guides["metric-dictionary"]).toContain(
      "never presented as stores sold",
    );
    expect(guides.limitations).toContain(
      "distinct positive-price store-level search results",
    );
    expect(guides["change-orders"]).toContain("2026-09-08");
    expect(guides["change-orders"]).toContain(
      "restored the owner-defined positive-price search footprint",
    );
    expect(guides.matching).toContain(
      "counts distinct normalized store keys when the exact product appears",
    );
    expect(guides.matching).toContain(
      "service-area presence is counted separately",
    );
    expect(guides["change-orders"]).toContain("does not use stock status");
    expect(guides["change-orders"]).toContain(
      "no result is extrapolated to an unobserved store",
    );
    expect(guides["change-orders"]).toContain(
      "match certification administration exposes reprocess retained evidence with a required reason",
    );
    expect(guides["change-orders"]).toContain(
      "new immutable replay generation with zero collection, provider, or ai calls",
    );
    expect(guides["analytics-reporting"]).toContain(
      "not imported by the live /analyses/[analysisid] page",
    );
    expect(guides["analytics-reporting"]).toContain(
      "complete walmart-win and walmart-loss action lists",
    );
    expect(guides["change-orders"]).toContain(
      "csv, excel-compatible, and json downloads",
    );
    expect(guides["change-orders"]).toContain(
      "searched-not-observed store locations",
    );
    expect(guides["change-orders"]).toContain(
      "instead of rebuilding the full retailer catalog",
    );
    expect(guides["analytics-reporting"]).toContain(
      "product/store-evidence drawers",
    );
    expect(guides["change-orders"]).toContain(
      "does not drop account/rbac database tables",
    );
    expect(guides["change-orders"]).toContain(
      "does not drop account/rbac database tables, remove railway workos secrets",
    );
    expect(guides["analytics-reporting"]).toContain("state-footprint context");
    expect(guides["analytics-reporting"]).toContain("source-backed filters");
    expect(guides["analytics-reporting"]).toContain(
      "a normalized $/gallon value is never labeled as shelf or package price",
    );
    expect(guides["change-orders"]).toContain(
      "state_filter plus visible filtered row counts",
    );
    expect(guides["change-orders"]).toContain(
      "business footprint share from searched-row audit share",
    );
    expect(guides["change-orders"]).toContain(
      "largest observed positive-price store footprint for that retailer",
    );
    expect(guides["change-orders"]).toContain(
      "not total chain stores, inventory, or a sampled returned-row count",
    );
    expect(guides["change-orders"]).toContain(
      "broad distribution as a metric, not a hidden filter",
    );
  });
});
