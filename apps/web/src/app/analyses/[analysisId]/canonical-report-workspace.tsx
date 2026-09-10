"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import type { RetailCompetitiveIntelligenceCanonicalReportDataset } from "@rci/contracts";
import type { GeometryCollection, Topology } from "topojson-specification";
import { feature } from "topojson-client";
import statesTopologySource from "us-atlas/states-10m.json";

import type {
  AnalysisRecord,
  AnalysisReportView,
  PriceMonitoringMap,
} from "@/lib/api";
import { canonicalReportDatasetFromReportView } from "@/lib/canonical-report-dataset";
import {
  BROAD_WALMART_DISTRIBUTION_THRESHOLD,
  DEFAULT_CANONICAL_RELATIONSHIP_FILTERS,
  type CanonicalRelationshipFilters,
  type CanonicalPriceBasis,
  canonicalBenchmarkBrandOptions,
  canonicalComparisonBasisOptions,
  canonicalCompetitorBrandOptions,
  canonicalCompetitorOptions,
  canonicalRelationshipPriceBasis,
  canonicalUnitBasisOptions,
  filterCanonicalRelationships,
  groupCanonicalRelationshipsByOutcome,
  summarizeCanonicalBrandTypes,
} from "@/lib/canonical-report-focus";
import {
  canonicalReportChecklist,
  canonicalReportIntegrityIssues,
} from "@/lib/canonical-report-qa";
import { displayDate, displayLabel } from "@/lib/presentation";

type CanonicalDataset = RetailCompetitiveIntelligenceCanonicalReportDataset;
type ProductRelationship = CanonicalDataset["product_relationships"][number];
type BenchmarkProduct = ProductRelationship["benchmark_product"];
type ReportProduct =
  | ProductRelationship["benchmark_product"]
  | ProductRelationship["competitor_product"];
type BrandType = ProductRelationship["benchmark_product"]["brand_type"];
type PriceMonitoringMapPoint = PriceMonitoringMap["points"][number];
type ExecutiveOutcomeMode = "losses" | "wins";
type RelationshipSectionMode = "losses" | "wins" | "parity";
type ProductEvidenceTarget = {
  product: ReportProduct;
  reportFootprintCount?: number | null;
  retailerLabel: string;
  roleLabel: string;
};
type StateFeature = {
  id?: string | number;
  geometry: { type: string; coordinates: unknown };
};
type ProductFootprint = {
  product: BenchmarkProduct;
  relationships: ProductRelationship[];
  walmartWins: number;
  walmartLosses: number;
  parityOrUnscored: number;
  competitorRetailers: string[];
  largestLoss: ProductRelationship | null;
  strongestWin: ProductRelationship | null;
};

const canonicalTabs = [
  "Executive Summary",
  "Product Wins & Losses",
  "Distribution & Assortment",
  "Price Architecture",
  "Evidence & QA",
] as const;

type CanonicalTab = (typeof canonicalTabs)[number];

const brandTypeLabels: Record<BrandType, string> = {
  private_label: "Private label",
  regional: "Regional",
  national: "National",
  unclassified: "Unclassified",
};

const outcomeLabels: Record<
  ProductRelationship["comparison"]["outcome"],
  string
> = {
  walmart_wins: "Walmart wins",
  competitor_wins: "Walmart loses",
  parity: "Parity",
  unscored: "Unscored",
};

function formatCurrency(value: number) {
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatPercent(value: number) {
  return value.toLocaleString("en-US", {
    maximumFractionDigits: 1,
    minimumFractionDigits: 1,
    style: "percent",
  });
}

function formatSignedCurrency(value: number) {
  if (Math.abs(value) < 0.005) return "$0.00";
  return `${value > 0 ? "+" : "-"}${formatCurrency(Math.abs(value))}`;
}

function priceBasisLabel(priceBasis: CanonicalPriceBasis) {
  if (priceBasis === "package_price") return "Package price";
  if (priceBasis === "mixed_price_basis") return "Mixed price basis";
  return "Normalized comparison value";
}

function priceDisplay(product: ReportProduct) {
  const packagePrice = product.price.package_price;
  if (
    typeof packagePrice === "number" &&
    Number.isFinite(packagePrice) &&
    packagePrice > 0
  ) {
    return {
      primary: formatCurrency(packagePrice),
      secondary: product.price.normalized_unit_price
        ? `Normalized comparison: ${product.price.reporting_price_label}`
        : "Source-backed package price",
    };
  }
  return {
    primary: `Normalized comparison: ${product.price.reporting_price_label}`,
    secondary:
      "Pack/shelf price was not supplied in this report dataset; do not read as shelf price.",
  };
}

function retailerFootprintsFromRelationships(
  relationships: ProductRelationship[],
) {
  const footprints = new Map<string, number>();
  for (const relationship of relationships) {
    for (const product of [
      relationship.benchmark_product,
      relationship.competitor_product,
    ]) {
      const count = product.distribution.physical_store_distribution_count;
      footprints.set(
        product.retailer_id,
        Math.max(footprints.get(product.retailer_id) ?? 0, count),
      );
    }
  }
  return footprints;
}

function reportFootprintCountFor(
  product: ReportProduct,
  retailerFootprints: Map<string, number>,
) {
  const footprint = retailerFootprints.get(product.retailer_id) ?? null;
  return footprint && footprint > 0 ? footprint : null;
}

function reportFootprintLabel(
  product: ReportProduct,
  reportFootprintCount?: number | null,
) {
  const storeCount = product.distribution.physical_store_distribution_count;
  if (reportFootprintCount && reportFootprintCount > 0) {
    return `${storeCount.toLocaleString()} stores (${formatPercent(
      storeCount / reportFootprintCount,
    )} of ${reportFootprintCount.toLocaleString()} report footprint)`;
  }
  return `${storeCount.toLocaleString()} stores (report-footprint denominator unavailable)`;
}

function productEvidenceTarget(
  product: ReportProduct,
  retailerLabel: string,
  roleLabel: string,
  retailerFootprints: Map<string, number>,
): ProductEvidenceTarget {
  return {
    product,
    reportFootprintCount: reportFootprintCountFor(product, retailerFootprints),
    retailerLabel,
    roleLabel,
  };
}

function searchedStoreCountFromMap(mapData: PriceMonitoringMap | null) {
  if (!mapData) return null;
  const searchedStores =
    mapData.display.distribution_store_count +
    mapData.display.not_observed_locations;
  return searchedStores > 0 ? searchedStores : null;
}

function mapEvidenceHref(
  analysisId: string,
  product: ReportProduct,
  detail: "summary" | "full" = "full",
) {
  const parameters = new URLSearchParams({
    retailer: product.retailer_id,
    product_id: product.retailer_product_id,
    detail,
  });
  return `/api/price-monitoring/${encodeURIComponent(analysisId)}/map?${parameters.toString()}`;
}

function productHref(url: string | null) {
  return url && /^https?:\/\//i.test(url) ? url : null;
}

function byDistributionThenTitle(
  a: ProductRelationship,
  b: ProductRelationship,
) {
  return (
    b.benchmark_product.distribution.physical_store_distribution_count -
      a.benchmark_product.distribution.physical_store_distribution_count ||
    a.benchmark_product.title.localeCompare(b.benchmark_product.title)
  );
}

function relationshipGroups(dataset: CanonicalDataset) {
  return {
    walmartWins: dataset.product_relationships
      .filter(
        (row: ProductRelationship) => row.comparison.outcome === "walmart_wins",
      )
      .sort(byDistributionThenTitle),
    walmartLosses: dataset.product_relationships
      .filter(
        (row: ProductRelationship) =>
          row.comparison.outcome === "competitor_wins",
      )
      .sort(byDistributionThenTitle),
    parity: dataset.product_relationships
      .filter(
        (row: ProductRelationship) =>
          row.comparison.outcome === "parity" ||
          row.comparison.outcome === "unscored",
      )
      .sort(byDistributionThenTitle),
  };
}

function brandTypeGroups(dataset: CanonicalDataset) {
  return (Object.keys(brandTypeLabels) as BrandType[]).map((brandType) => ({
    brandType,
    relationships: dataset.product_relationships
      .filter(
        (row: ProductRelationship) =>
          row.benchmark_product.brand_type === brandType,
      )
      .sort(byDistributionThenTitle),
  }));
}

function productMonitoringHref(
  analysisId: string,
  product: ReportProduct,
  tab = "overview",
) {
  const parameters = new URLSearchParams({
    retailer: product.retailer_id,
    product_id: product.retailer_product_id,
    tab,
  });
  return `/price-monitoring/${encodeURIComponent(analysisId)}?${parameters.toString()}`;
}

function productEvidenceCsvHref(analysisId: string, product: ReportProduct) {
  const parameters = new URLSearchParams({
    retailer: product.retailer_id,
    product_id: product.retailer_product_id,
  });
  return `/api/price-monitoring/${encodeURIComponent(analysisId)}/evidence.csv?${parameters.toString()}`;
}

function safeDownloadName(value: string) {
  return value.replace(/[^a-z0-9._-]+/gi, "-").replace(/^-+|-+$/g, "");
}

function escapeXml(value: string | number | boolean | null) {
  if (value === null) return "";
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function downloadTextFile(filename: string, text: string, type: string) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function storeEvidenceRows(mapData: PriceMonitoringMap | null) {
  return (mapData?.points ?? []).filter(
    (point) => point.status === "observed" && point.kind === "store",
  );
}

function searchedStoreRows(mapData: PriceMonitoringMap | null) {
  return (mapData?.points ?? []).filter((point) => point.kind === "store");
}

function exportableStoreRows(points: PriceMonitoringMapPoint[]) {
  return points.map((point) => ({
    evidence_status: point.status,
    included_in_distribution: point.status === "observed",
    scope_key: point.scope_key,
    store_number: point.store_number,
    store_name: point.store_name,
    distribution_store_id: point.distribution_store_id,
    city: point.city,
    state: point.state,
    zipcode: point.zipcode,
    country: point.country,
    latitude: point.latitude,
    longitude: point.longitude,
    search_price: point.price,
    difference_from_reference: point.difference_from_reference,
    search_observed: point.search_observed,
    is_sponsored: point.is_sponsored,
  }));
}

function stateOptionsFromPoints(points: PriceMonitoringMapPoint[]) {
  return Array.from(
    new Set(
      points
        .map((point) => point.state)
        .filter((state): state is string => Boolean(state?.trim())),
    ),
  ).sort((left, right) => left.localeCompare(right, "en-US"));
}

function csvCell(value: unknown) {
  const raw = value === null || value === undefined ? "" : String(value);
  const safe =
    typeof value === "string" && /^[=+\-@]/.test(raw) ? `'${raw}` : raw;
  return `"${safe.replaceAll('"', '""')}"`;
}

function rowsToCsv(rows: Array<Record<string, unknown>>) {
  const columns = Object.keys(
    rows[0] ?? {
      evidence_status: "",
      included_in_distribution: "",
      scope_key: "",
      store_number: "",
      store_name: "",
      distribution_store_id: "",
      city: "",
      state: "",
      zipcode: "",
      country: "",
      latitude: "",
      longitude: "",
      search_price: "",
      difference_from_reference: "",
      search_observed: "",
      is_sponsored: "",
    },
  );
  return [
    columns.join(","),
    ...rows.map((row) =>
      columns.map((column) => csvCell(row[column])).join(","),
    ),
  ].join("\r\n");
}

function summarizeProductFootprints(
  relationships: ProductRelationship[],
): ProductFootprint[] {
  const grouped = new Map<string, ProductRelationship[]>();
  for (const relationship of relationships) {
    const productId = relationship.benchmark_product.retailer_product_id;
    grouped.set(productId, [...(grouped.get(productId) ?? []), relationship]);
  }
  return [...grouped.values()]
    .map((rows) => {
      const product = rows[0]!.benchmark_product;
      const losses = rows.filter(
        (row) => row.comparison.outcome === "competitor_wins",
      );
      const wins = rows.filter(
        (row) => row.comparison.outcome === "walmart_wins",
      );
      return {
        product,
        relationships: rows,
        walmartWins: wins.length,
        walmartLosses: losses.length,
        parityOrUnscored: rows.filter(
          (row) =>
            row.comparison.outcome === "parity" ||
            row.comparison.outcome === "unscored",
        ).length,
        competitorRetailers: [
          ...new Set(rows.map((row) => row.competitor_product.retailer_id)),
        ].sort(),
        largestLoss:
          losses.sort(
            (left, right) =>
              Math.abs(right.comparison.price_delta_percent) -
                Math.abs(left.comparison.price_delta_percent) ||
              right.benchmark_product.distribution
                .physical_store_distribution_count -
                left.benchmark_product.distribution
                  .physical_store_distribution_count,
          )[0] ?? null,
        strongestWin:
          wins.sort(
            (left, right) =>
              Math.abs(right.comparison.price_delta_percent) -
                Math.abs(left.comparison.price_delta_percent) ||
              right.benchmark_product.distribution
                .physical_store_distribution_count -
                left.benchmark_product.distribution
                  .physical_store_distribution_count,
          )[0] ?? null,
      };
    })
    .sort(
      (left, right) =>
        right.product.distribution.physical_store_distribution_count -
          left.product.distribution.physical_store_distribution_count ||
        right.walmartLosses - left.walmartLosses ||
        left.product.title.localeCompare(right.product.title),
    );
}

export function CanonicalReportWorkspace({
  analysis,
  reportView,
}: Readonly<{
  analysis: AnalysisRecord;
  reportView: AnalysisReportView;
}>) {
  const [activeTab, setActiveTab] = useState<CanonicalTab>(canonicalTabs[0]);
  const dataset = useMemo(
    () => canonicalReportDatasetFromReportView(analysis, reportView),
    [analysis, reportView],
  );
  const groups = useMemo(() => relationshipGroups(dataset), [dataset]);
  const brandGroups = useMemo(() => brandTypeGroups(dataset), [dataset]);
  const retailerFootprints = useMemo(
    () => retailerFootprintsFromRelationships(dataset.product_relationships),
    [dataset.product_relationships],
  );
  const productFootprints = useMemo(
    () => summarizeProductFootprints(dataset.product_relationships),
    [dataset.product_relationships],
  );
  const brandTypeSummary = useMemo(
    () => summarizeCanonicalBrandTypes(dataset.product_relationships),
    [dataset.product_relationships],
  );
  const integrityIssues = useMemo(
    () => canonicalReportIntegrityIssues(dataset),
    [dataset],
  );
  const broadWalmartRelationships = useMemo(
    () =>
      dataset.product_relationships
        .filter(
          (relationship: ProductRelationship) =>
            relationship.benchmark_product.distribution
              .physical_store_distribution_count >=
            BROAD_WALMART_DISTRIBUTION_THRESHOLD,
        )
        .sort(byDistributionThenTitle),
    [dataset.product_relationships],
  );

  return (
    <>
      <header className="workspace-header report-header canonical-report-header">
        <div>
          <p className="eyebrow">Product-level report</p>
          <h1>{dataset.product_pack.name}</h1>
          <p className="report-deck">
            Product-level price intelligence built from governed relationships,
            positive-price store distribution, qualified seller rules, and
            explicit price-normalization guardrails.
          </p>
          <p className="workspace-meta">
            {analysis.analysis_id} · Generated{" "}
            {displayDate(dataset.generated_at)}
            {dataset.evidence_observed_at !== dataset.generated_at
              ? ` · Evidence through ${displayDate(dataset.evidence_observed_at)}`
              : ""}
          </p>
          <div className="trust-strip" aria-label="Report contracts">
            <span>No inventory claims</span>
            <span>Zero prices treated as missing</span>
            <span>Seller governed</span>
            <span>Canonical dataset</span>
          </div>
        </div>
        <div className="workspace-status">
          <span className={`status-badge ${dataset.readiness.status}`}>
            {displayLabel(dataset.readiness.status)}
          </span>
          <small>Canonical dataset {dataset.schema_version}</small>
          <Link
            className="canonical-dataset-link"
            href={`/analyses/${encodeURIComponent(analysis.analysis_id)}?experience=legacy`}
          >
            Legacy workspace
          </Link>
          <Link
            className="canonical-dataset-link"
            href={`/api/analyses/${encodeURIComponent(analysis.analysis_id)}/canonical-report-dataset`}
            target="_blank"
            rel="noreferrer"
          >
            Dataset JSON
          </Link>
        </div>
      </header>

      <div className="tab-list" role="tablist" aria-label="Report sections">
        {canonicalTabs.map((tab) => (
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === tab}
            className={activeTab === tab ? "active" : ""}
            onClick={() => setActiveTab(tab)}
            key={tab}
          >
            {tab}
          </button>
        ))}
      </div>

      <section className="workspace-panel" role="tabpanel">
        {activeTab === "Executive Summary" ? (
          <ExecutiveSummary
            analysisId={analysis.analysis_id}
            dataset={dataset}
            groups={groups}
            brandTypeSummary={brandTypeSummary}
            retailerFootprints={retailerFootprints}
          />
        ) : null}
        {activeTab === "Product Wins & Losses" ? (
          <ProductWinsLosses
            dataset={dataset}
            retailerFootprints={retailerFootprints}
          />
        ) : null}
        {activeTab === "Distribution & Assortment" ? (
          <DistributionAssortment
            analysisId={analysis.analysis_id}
            productFootprints={productFootprints}
            retailerFootprints={retailerFootprints}
            broadWalmartProductCount={
              productFootprints.filter(
                (row) =>
                  row.product.distribution.physical_store_distribution_count >=
                  BROAD_WALMART_DISTRIBUTION_THRESHOLD,
              ).length
            }
            broadWalmartRelationshipCount={broadWalmartRelationships.length}
            totalRelationships={dataset.product_relationships.length}
          />
        ) : null}
        {activeTab === "Price Architecture" ? (
          <PriceArchitecture
            analysisId={analysis.analysis_id}
            brandGroups={brandGroups}
            relationships={dataset.product_relationships}
            retailerFootprints={retailerFootprints}
          />
        ) : null}
        {activeTab === "Evidence & QA" ? (
          <EvidenceQa dataset={dataset} integrityIssues={integrityIssues} />
        ) : null}
      </section>
    </>
  );
}

function ExecutiveSummary({
  analysisId,
  dataset,
  groups,
  brandTypeSummary,
  retailerFootprints,
}: Readonly<{
  analysisId: string;
  dataset: CanonicalDataset;
  groups: ReturnType<typeof relationshipGroups>;
  brandTypeSummary: ReturnType<typeof summarizeCanonicalBrandTypes>;
  retailerFootprints: Map<string, number>;
}>) {
  const actionSort = (left: ProductRelationship, right: ProductRelationship) =>
    right.benchmark_product.distribution.physical_store_distribution_count -
      left.benchmark_product.distribution.physical_store_distribution_count ||
    Math.abs(right.comparison.price_delta_percent) -
      Math.abs(left.comparison.price_delta_percent) ||
    left.benchmark_product.title.localeCompare(right.benchmark_product.title);
  const priorityLosses = [...groups.walmartLosses].sort(actionSort);
  const priorityWins = [...groups.walmartWins].sort(actionSort);
  const [outcomeMode, setOutcomeMode] =
    useState<ExecutiveOutcomeMode>("losses");
  const broadLosses = groups.walmartLosses.filter(
    (relationship) =>
      relationship.benchmark_product.distribution
        .physical_store_distribution_count >=
      BROAD_WALMART_DISTRIBUTION_THRESHOLD,
  );
  const broadWins = groups.walmartWins.filter(
    (relationship) =>
      relationship.benchmark_product.distribution
        .physical_store_distribution_count >=
      BROAD_WALMART_DISTRIBUTION_THRESHOLD,
  );
  const activeRelationships =
    outcomeMode === "losses" ? priorityLosses : priorityWins;
  const activeBroadCount =
    outcomeMode === "losses" ? broadLosses.length : broadWins.length;
  const activeTitle =
    outcomeMode === "losses"
      ? "Complete Walmart loss action list"
      : "Complete Walmart win action list";
  const activeEmptyLabel =
    outcomeMode === "losses"
      ? "No Walmart losses are available in the governed relationship set."
      : "No Walmart wins are available in the governed relationship set.";
  return (
    <>
      <section className="workspace-section">
        <header>
          <div>
            <h2>What matters now</h2>
            <p>
              This report prioritizes product-level decisions over rollups. A
              product is included only when its comparison price is positive,
              seller governance passes, and distribution evidence is valid.
            </p>
          </div>
        </header>
        <div className="metric-grid canonical-metric-grid">
          <Metric
            label="Included relationships"
            value={dataset.summary.relationship_count}
          />
          <Metric
            label="Walmart wins"
            value={dataset.summary.walmart_win_count}
          />
          <Metric
            label="Walmart losses"
            value={dataset.summary.competitor_win_count}
          />
          <Metric
            label="Excluded by guardrails"
            value={dataset.summary.excluded_relationship_count}
          />
        </div>
        <div className="canonical-callout-grid">
          <article>
            <span>Immediate attention</span>
            <strong>
              {groups.walmartLosses.length.toLocaleString()} Walmart losses
              surfaced
            </strong>
            <p>
              Losses are sorted by Walmart product distribution so nationally
              relevant items rise above niche/local comparisons.
            </p>
          </article>
          <article>
            <span>Defend</span>
            <strong>
              {groups.walmartWins.length.toLocaleString()} Walmart wins surfaced
            </strong>
            <p>
              Wins show where Walmart has a lower governed reporting price for
              the matched product relationship.
            </p>
          </article>
          <article>
            <span>Trust boundary</span>
            <strong>
              {dataset.qa.invalid_price_record_count.toLocaleString()} invalid
              price rows excluded
            </strong>
            <p>
              $0 regular or discounted values are treated as missing sentinels,
              never as a valid customer-facing price.
            </p>
          </article>
        </div>
      </section>
      <section className="workspace-section">
        <header>
          <div>
            <h2>{activeTitle}</h2>
            <p>
              Use the toggle to switch between the complete executive loss and
              win lists without scrolling past one list to reach the other. Rows
              are sorted by Walmart product footprint and price gap, and every
              row exposes Walmart and competitor store evidence.
            </p>
          </div>
          <div className="canonical-executive-actions">
            <div
              className="canonical-executive-toggle"
              role="group"
              aria-label="Executive summary outcome"
            >
              <button
                className={outcomeMode === "losses" ? "active" : ""}
                type="button"
                onClick={() => setOutcomeMode("losses")}
              >
                Losses ({priorityLosses.length.toLocaleString()})
              </button>
              <button
                className={outcomeMode === "wins" ? "active" : ""}
                type="button"
                onClick={() => setOutcomeMode("wins")}
              >
                Wins ({priorityWins.length.toLocaleString()})
              </button>
            </div>
            <span className="canonical-section-stat">
              {activeRelationships.length.toLocaleString()} total {outcomeMode}{" "}
              · {activeBroadCount.toLocaleString()} broad-footprint
            </span>
          </div>
        </header>
        <ExecutivePriorityTable
          analysisId={analysisId}
          emptyLabel={activeEmptyLabel}
          relationships={activeRelationships}
          retailerFootprints={retailerFootprints}
        />
      </section>
      <section className="workspace-section">
        <header>
          <div>
            <h2>Brand role focus</h2>
            <p>
              Counts below are factual summaries of included governed product
              relationships. Regional brand content remains fact-only.
            </p>
          </div>
        </header>
        {brandTypeSummary.length ? (
          <div className="canonical-brand-role-grid">
            {brandTypeSummary.map((summary) => (
              <article key={summary.brandType}>
                <span>{brandTypeLabels[summary.brandType]}</span>
                <strong>
                  {summary.relationships.toLocaleString()} included
                </strong>
                <p>
                  {summary.walmartLosses.toLocaleString()} Walmart losses ·{" "}
                  {summary.walmartWins.toLocaleString()} Walmart wins ·{" "}
                  {summary.broadWalmartLosses.toLocaleString()} broad-footprint
                  losses
                </p>
              </article>
            ))}
          </div>
        ) : (
          <p className="empty-note">
            No included relationships are available for brand-role review.
          </p>
        )}
      </section>
    </>
  );
}

function ExecutivePriorityTable({
  analysisId,
  emptyLabel,
  relationships,
  retailerFootprints,
}: Readonly<{
  analysisId: string;
  emptyLabel: string;
  relationships: ProductRelationship[];
  retailerFootprints: Map<string, number>;
}>) {
  const [selectedEvidenceTarget, setSelectedEvidenceTarget] =
    useState<ProductEvidenceTarget | null>(null);
  if (!relationships.length) {
    return <p className="empty-note">{emptyLabel}</p>;
  }
  return (
    <>
      <div className="canonical-table-wrap">
        <table className="canonical-insight-table canonical-executive-table">
          <thead>
            <tr>
              <th>Walmart product</th>
              <th>Competitor product</th>
              <th>Gap</th>
              <th>Store footprint</th>
              <th>Basis</th>
            </tr>
          </thead>
          <tbody>
            {relationships.map((relationship) => (
              <tr key={relationship.relationship_id}>
                <td>
                  <strong>{relationship.benchmark_product.title}</strong>
                  <span>
                    {relationship.benchmark_product.retailer_product_id} ·{" "}
                    {brandTypeLabels[relationship.benchmark_product.brand_type]}
                  </span>
                  <span>
                    {priceDisplay(relationship.benchmark_product).primary}
                  </span>
                  <span className="canonical-price-note">
                    {priceDisplay(relationship.benchmark_product).secondary}
                  </span>
                </td>
                <td>
                  <strong>{relationship.competitor_product.title}</strong>
                  <span>
                    {displayLabel(relationship.competitor_product.retailer_id)}{" "}
                    · {relationship.competitor_product.retailer_product_id}
                  </span>
                  <span>
                    {priceDisplay(relationship.competitor_product).primary}
                  </span>
                  <span className="canonical-price-note">
                    {priceDisplay(relationship.competitor_product).secondary}
                  </span>
                </td>
                <td>
                  <strong>
                    {formatSignedCurrency(relationship.comparison.price_delta)}
                  </strong>
                  <span>
                    {formatPercent(
                      Math.abs(relationship.comparison.price_delta_percent),
                    )}{" "}
                    {relationship.comparison.outcome === "walmart_wins"
                      ? "Walmart advantage"
                      : relationship.comparison.outcome === "competitor_wins"
                        ? "competitor advantage"
                        : "gap"}
                  </span>
                </td>
                <td>
                  <strong>
                    Walmart:{" "}
                    {reportFootprintLabel(
                      relationship.benchmark_product,
                      reportFootprintCountFor(
                        relationship.benchmark_product,
                        retailerFootprints,
                      ),
                    )}
                  </strong>
                  <span>
                    Competitor:{" "}
                    {reportFootprintLabel(
                      relationship.competitor_product,
                      reportFootprintCountFor(
                        relationship.competitor_product,
                        retailerFootprints,
                      ),
                    )}
                  </span>
                  <span className="canonical-table-actions">
                    <button
                      type="button"
                      onClick={() =>
                        setSelectedEvidenceTarget(
                          productEvidenceTarget(
                            relationship.benchmark_product,
                            "Walmart",
                            "Walmart store evidence",
                            retailerFootprints,
                          ),
                        )
                      }
                    >
                      Walmart stores
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        setSelectedEvidenceTarget(
                          productEvidenceTarget(
                            relationship.competitor_product,
                            displayLabel(
                              relationship.competitor_product.retailer_id,
                            ),
                            "Competitor store evidence",
                            retailerFootprints,
                          ),
                        )
                      }
                    >
                      Competitor stores
                    </button>
                  </span>
                </td>
                <td>
                  <strong>{relationship.comparison.unit_basis}</strong>
                  <span>{relationship.comparison.comparison_basis}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {selectedEvidenceTarget ? (
        <StoreEvidenceDrawer
          analysisId={analysisId}
          target={selectedEvidenceTarget}
          onClose={() => setSelectedEvidenceTarget(null)}
        />
      ) : null}
    </>
  );
}

function ProductWinsLosses({
  dataset,
  retailerFootprints,
}: Readonly<{
  dataset: CanonicalDataset;
  retailerFootprints: Map<string, number>;
}>) {
  const [filters, setFilters] = useState<CanonicalRelationshipFilters>(
    DEFAULT_CANONICAL_RELATIONSHIP_FILTERS,
  );
  const [filterDrawerOpen, setFilterDrawerOpen] = useState(false);
  const [sectionMode, setSectionMode] =
    useState<RelationshipSectionMode>("losses");
  const competitorOptions = useMemo(
    () => canonicalCompetitorOptions(dataset.product_relationships),
    [dataset.product_relationships],
  );
  const benchmarkBrandOptions = useMemo(
    () => canonicalBenchmarkBrandOptions(dataset.product_relationships),
    [dataset.product_relationships],
  );
  const competitorBrandOptions = useMemo(
    () => canonicalCompetitorBrandOptions(dataset.product_relationships),
    [dataset.product_relationships],
  );
  const comparisonBasisOptions = useMemo(
    () => canonicalComparisonBasisOptions(dataset.product_relationships),
    [dataset.product_relationships],
  );
  const unitBasisOptions = useMemo(
    () => canonicalUnitBasisOptions(dataset.product_relationships),
    [dataset.product_relationships],
  );
  const filteredRelationships = useMemo(
    () => filterCanonicalRelationships(dataset.product_relationships, filters),
    [dataset.product_relationships, filters],
  );
  const groups = useMemo(
    () => groupCanonicalRelationshipsByOutcome(filteredRelationships),
    [filteredRelationships],
  );
  const updateFilters = (
    patch: Partial<CanonicalRelationshipFilters>,
  ): void => {
    setFilters((current) => ({ ...current, ...patch }));
  };
  const resetFilters = () => setFilters(DEFAULT_CANONICAL_RELATIONSHIP_FILTERS);
  const activeFilterCount = [
    filters.query.trim(),
    filters.outcome !== "all",
    filters.brandType !== "all",
    filters.benchmarkBrand !== "all",
    filters.competitorBrand !== "all",
    filters.competitorRetailerId !== "all",
    filters.comparisonBasis !== "all",
    filters.unitBasis !== "all",
    filters.priceBasis !== "all",
    filters.minimumWalmartDistribution > 0,
    filters.sort !== DEFAULT_CANONICAL_RELATIONSHIP_FILTERS.sort,
  ].filter(Boolean).length;
  const activeSection =
    sectionMode === "losses"
      ? {
          title: `All Walmart losses (${groups.walmartLosses.length.toLocaleString()})`,
          note: "These are all included competitor-win relationships matching the active filters, not illustrative examples.",
          relationships: groups.walmartLosses,
        }
      : sectionMode === "wins"
        ? {
            title: `All Walmart wins (${groups.walmartWins.length.toLocaleString()})`,
            note: "These are all included Walmart-win relationships matching the active filters, not illustrative examples.",
            relationships: groups.walmartWins,
          }
        : {
            title: `Parity / unscored (${groups.parity.length.toLocaleString()})`,
            note: "Shown separately so parity does not dilute the action list.",
            relationships: groups.parity,
          };

  return (
    <>
      <section className="workspace-section canonical-browser-section">
        <header>
          <div>
            <h2>Product action board</h2>
            <p>
              Default view includes every governed relationship. Use filters to
              focus the same image cards by brand, retailer, outcome, comparison
              basis, price basis, distribution footprint, or product text.
            </p>
          </div>
          <div className="canonical-filter-actions">
            <button
              type="button"
              className="canonical-dataset-link"
              onClick={() => setFilterDrawerOpen(true)}
            >
              Filters
              {activeFilterCount ? ` (${activeFilterCount})` : ""}
            </button>
            <button type="button" className="text-link" onClick={resetFilters}>
              Reset filters
            </button>
          </div>
        </header>
        <div className="canonical-filter-summary-row">
          <label className="canonical-quick-search">
            <span>Quick search</span>
            <input
              type="search"
              value={filters.query}
              placeholder="Name, brand, product ID…"
              onChange={(event) => updateFilters({ query: event.target.value })}
            />
          </label>
          <div
            className="canonical-executive-toggle"
            role="group"
            aria-label="Card section"
          >
            <button
              className={sectionMode === "losses" ? "active" : ""}
              type="button"
              onClick={() => setSectionMode("losses")}
            >
              Losses ({groups.walmartLosses.length.toLocaleString()})
            </button>
            <button
              className={sectionMode === "wins" ? "active" : ""}
              type="button"
              onClick={() => setSectionMode("wins")}
            >
              Wins ({groups.walmartWins.length.toLocaleString()})
            </button>
            <button
              className={sectionMode === "parity" ? "active" : ""}
              type="button"
              onClick={() => setSectionMode("parity")}
            >
              Parity ({groups.parity.length.toLocaleString()})
            </button>
          </div>
        </div>
        <p className="canonical-browser-summary">
          Showing {filteredRelationships.length.toLocaleString()} of{" "}
          {dataset.product_relationships.length.toLocaleString()} included
          relationships · {groups.walmartLosses.length.toLocaleString()} losses
          · {groups.walmartWins.length.toLocaleString()} wins ·{" "}
          {groups.parity.length.toLocaleString()} parity/unscored. Category:{" "}
          {dataset.product_pack.name}. Store-state filtering is available in the
          exact product location drawers where state evidence exists.
        </p>
      </section>
      <RelationshipSection
        analysisId={dataset.analysis_id}
        title={activeSection.title}
        note={activeSection.note}
        relationships={activeSection.relationships}
        retailerFootprints={retailerFootprints}
      />
      {filterDrawerOpen ? (
        <RelationshipFilterDrawer
          benchmarkBrandOptions={benchmarkBrandOptions}
          categoryLabel={dataset.product_pack.name}
          comparisonBasisOptions={comparisonBasisOptions}
          competitorBrandOptions={competitorBrandOptions}
          competitorOptions={competitorOptions}
          filters={filters}
          onClose={() => setFilterDrawerOpen(false)}
          onReset={resetFilters}
          onUpdate={updateFilters}
          unitBasisOptions={unitBasisOptions}
        />
      ) : null}
    </>
  );
}

function RelationshipFilterDrawer({
  benchmarkBrandOptions,
  categoryLabel,
  comparisonBasisOptions,
  competitorBrandOptions,
  competitorOptions,
  filters,
  onClose,
  onReset,
  onUpdate,
  unitBasisOptions,
}: Readonly<{
  benchmarkBrandOptions: string[];
  categoryLabel: string;
  comparisonBasisOptions: string[];
  competitorBrandOptions: string[];
  competitorOptions: string[];
  filters: CanonicalRelationshipFilters;
  onClose: () => void;
  onReset: () => void;
  onUpdate: (patch: Partial<CanonicalRelationshipFilters>) => void;
  unitBasisOptions: string[];
}>) {
  return (
    <div className="pm-drawer-layer canonical-filter-drawer-layer">
      <button
        aria-label="Close filters"
        className="pm-drawer-backdrop"
        onClick={onClose}
        type="button"
      />
      <aside
        className="pm-product-drawer canonical-filter-drawer"
        role="dialog"
        aria-modal="true"
      >
        <header>
          <div>
            <p className="section-kicker">Report filters</p>
            <h2>Focus product relationships</h2>
            <small>
              Filters use fields already present in the canonical relationship
              dataset. State is applied inside exact-product store evidence
              drawers after location rows load.
            </small>
          </div>
          <button aria-label="Close filters" onClick={onClose} type="button">
            ×
          </button>
        </header>
        <div className="canonical-filter-grid">
          <label>
            <span>Search products</span>
            <input
              type="search"
              value={filters.query}
              placeholder="Name, brand, product ID…"
              onChange={(event) => onUpdate({ query: event.target.value })}
            />
          </label>
          <label>
            <span>Outcome</span>
            <select
              value={filters.outcome}
              onChange={(event) =>
                onUpdate({
                  outcome: event.target
                    .value as CanonicalRelationshipFilters["outcome"],
                })
              }
            >
              <option value="all">All outcomes</option>
              <option value="competitor_wins">Walmart losses</option>
              <option value="walmart_wins">Walmart wins</option>
              <option value="parity">Parity</option>
              <option value="unscored">Unscored</option>
            </select>
          </label>
          <label>
            <span>Walmart brand</span>
            <select
              value={filters.benchmarkBrand}
              onChange={(event) =>
                onUpdate({ benchmarkBrand: event.target.value })
              }
            >
              <option value="all">All Walmart brands</option>
              {benchmarkBrandOptions.map((brand) => (
                <option key={brand} value={brand}>
                  {brand}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Walmart brand type</span>
            <select
              value={filters.brandType}
              onChange={(event) =>
                onUpdate({
                  brandType: event.target
                    .value as CanonicalRelationshipFilters["brandType"],
                })
              }
            >
              <option value="all">All brand types</option>
              {(Object.keys(brandTypeLabels) as BrandType[]).map(
                (brandType) => (
                  <option key={brandType} value={brandType}>
                    {brandTypeLabels[brandType]}
                  </option>
                ),
              )}
            </select>
          </label>
          <label>
            <span>Retailer</span>
            <select
              value={filters.competitorRetailerId}
              onChange={(event) =>
                onUpdate({ competitorRetailerId: event.target.value })
              }
            >
              <option value="all">All competitor retailers</option>
              {competitorOptions.map((competitor) => (
                <option key={competitor} value={competitor}>
                  {displayLabel(competitor)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Competitor brand</span>
            <select
              value={filters.competitorBrand}
              onChange={(event) =>
                onUpdate({ competitorBrand: event.target.value })
              }
            >
              <option value="all">All competitor brands</option>
              {competitorBrandOptions.map((brand) => (
                <option key={brand} value={brand}>
                  {brand}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Category</span>
            <input readOnly value={categoryLabel} />
          </label>
          <label>
            <span>Subcategory</span>
            <input
              readOnly
              value="Not supplied by canonical dataset"
              aria-label="Subcategory not supplied by canonical dataset"
            />
          </label>
          <label>
            <span>State</span>
            <input
              readOnly
              value="Available in store evidence drawer"
              aria-label="State filter available in store evidence drawer"
            />
          </label>
          <label>
            <span>Comparison basis</span>
            <select
              value={filters.comparisonBasis}
              onChange={(event) =>
                onUpdate({ comparisonBasis: event.target.value })
              }
            >
              <option value="all">All comparison bases</option>
              {comparisonBasisOptions.map((basis) => (
                <option key={basis} value={basis}>
                  {displayLabel(basis)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Unit basis</span>
            <select
              value={filters.unitBasis}
              onChange={(event) => onUpdate({ unitBasis: event.target.value })}
            >
              <option value="all">All unit bases</option>
              {unitBasisOptions.map((basis) => (
                <option key={basis} value={basis}>
                  {displayLabel(basis)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Price basis</span>
            <select
              value={filters.priceBasis}
              onChange={(event) =>
                onUpdate({
                  priceBasis: event.target
                    .value as CanonicalRelationshipFilters["priceBasis"],
                })
              }
            >
              <option value="all">All price bases</option>
              <option value="comparison_unit_price">
                Normalized comparison values
              </option>
              <option value="package_price">Package prices</option>
              <option value="mixed_price_basis">Mixed price basis</option>
            </select>
          </label>
          <label>
            <span>Walmart footprint</span>
            <select
              value={filters.minimumWalmartDistribution}
              onChange={(event) =>
                onUpdate({
                  minimumWalmartDistribution: Number(event.target.value),
                })
              }
            >
              <option value={0}>All distribution levels</option>
              <option value={100}>100+ positive-price stores</option>
              <option value={BROAD_WALMART_DISTRIBUTION_THRESHOLD}>
                1,000+ positive-price stores
              </option>
            </select>
          </label>
          <label>
            <span>Sort</span>
            <select
              value={filters.sort}
              onChange={(event) =>
                onUpdate({
                  sort: event.target
                    .value as CanonicalRelationshipFilters["sort"],
                })
              }
            >
              <option value="action_priority">Action priority</option>
              <option value="distribution_desc">Walmart distribution</option>
              <option value="gap_desc">Largest percent gap</option>
              <option value="title_asc">Product title</option>
            </select>
          </label>
        </div>
        <div className="canonical-filter-drawer-actions">
          <button type="button" className="text-link" onClick={onReset}>
            Reset all
          </button>
          <button
            type="button"
            className="canonical-dataset-link"
            onClick={onClose}
          >
            Apply filters
          </button>
        </div>
      </aside>
    </div>
  );
}

function DistributionAssortment({
  analysisId,
  productFootprints,
  retailerFootprints,
  broadWalmartProductCount,
  broadWalmartRelationshipCount,
  totalRelationships,
}: Readonly<{
  analysisId: string;
  productFootprints: ProductFootprint[];
  retailerFootprints: Map<string, number>;
  broadWalmartProductCount: number;
  broadWalmartRelationshipCount: number;
  totalRelationships: number;
}>) {
  const [selectedProductId, setSelectedProductId] = useState(
    productFootprints[0]?.product.retailer_product_id ?? "",
  );
  const selectedFootprint =
    productFootprints.find(
      (row) => row.product.retailer_product_id === selectedProductId,
    ) ??
    productFootprints[0] ??
    null;

  return (
    <>
      <section className="workspace-section">
        <header>
          <div>
            <h2>Distribution and location evidence</h2>
            <p>
              Store distribution means distinct stores where the Walmart product
              appears in store-level Search with price greater than zero. It is
              not an in-stock indicator.
            </p>
          </div>
        </header>
        <div className="canonical-callout-grid">
          <article>
            <span>Broadly distributed</span>
            <strong>{broadWalmartProductCount.toLocaleString()}</strong>
            <p>
              Walmart products with at least 1,000 positive-price stores across{" "}
              {broadWalmartRelationshipCount.toLocaleString()} included
              relationships.
            </p>
          </article>
          <article>
            <span>Distribution rule</span>
            <strong>price &gt; 0 store Search presence</strong>
            <p>
              Service-area presence is tracked separately and is never displayed
              as a store count.
            </p>
          </article>
          <article>
            <span>Population</span>
            <strong>{totalRelationships.toLocaleString()} relationships</strong>
            <p>
              Product footprints below deduplicate repeated competitor
              relationships back to the exact Walmart product ID.
            </p>
          </article>
        </div>
      </section>
      <section className="workspace-section">
        <header>
          <div>
            <h2>Exact-product map</h2>
            <p>
              Select any Walmart product to load its source-backed location
              evidence map. Counts are distribution/search-presence counts, not
              inventory or in-stock status.
            </p>
          </div>
          {selectedFootprint ? (
            <div className="canonical-location-actions">
              <Link
                className="canonical-dataset-link"
                href={productMonitoringHref(
                  analysisId,
                  selectedFootprint.product,
                  "overview",
                )}
                target="_blank"
                rel="noreferrer"
              >
                Open full location view
              </Link>
              <Link
                className="canonical-dataset-link"
                href={productEvidenceCsvHref(
                  analysisId,
                  selectedFootprint.product,
                )}
                target="_blank"
                rel="noreferrer"
              >
                Download evidence CSV
              </Link>
            </div>
          ) : null}
        </header>
        {productFootprints.length ? (
          <>
            <label className="canonical-product-selector">
              <span>Walmart product</span>
              <select
                value={selectedFootprint?.product.retailer_product_id ?? ""}
                onChange={(event) => setSelectedProductId(event.target.value)}
              >
                {productFootprints.map((row) => (
                  <option
                    value={row.product.retailer_product_id}
                    key={row.product.retailer_product_id}
                  >
                    {row.product.title} ·{" "}
                    {reportFootprintLabel(
                      row.product,
                      reportFootprintCountFor(row.product, retailerFootprints),
                    )}
                  </option>
                ))}
              </select>
            </label>
            {selectedFootprint ? (
              <ProductLocationEvidencePanel
                analysisId={analysisId}
                footprint={selectedFootprint}
                retailerFootprints={retailerFootprints}
              />
            ) : null}
          </>
        ) : (
          <p className="empty-note">
            No Walmart products have governed location evidence in this
            relationship set.
          </p>
        )}
      </section>
      <section className="workspace-section">
        <header>
          <div>
            <h2>Product footprint table</h2>
            <p>
              One row per Walmart product ID, with all matched competitors
              summarized as counts so distribution is not overstated by repeated
              relationship rows.
            </p>
          </div>
        </header>
        <ProductFootprintTable
          analysisId={analysisId}
          retailerFootprints={retailerFootprints}
          rows={productFootprints}
        />
      </section>
    </>
  );
}

function ProductFootprintTable({
  analysisId,
  retailerFootprints,
  rows,
}: Readonly<{
  analysisId: string;
  retailerFootprints: Map<string, number>;
  rows: ProductFootprint[];
}>) {
  const [selectedEvidenceTarget, setSelectedEvidenceTarget] =
    useState<ProductEvidenceTarget | null>(null);
  if (!rows.length) {
    return (
      <p className="empty-note">
        No product footprints are available in this governed relationship set.
      </p>
    );
  }
  return (
    <>
      <div className="canonical-table-wrap">
        <table className="canonical-insight-table canonical-footprint-table">
          <thead>
            <tr>
              <th>Walmart product</th>
              <th>Footprint</th>
              <th>Relationships</th>
              <th>Largest loss / strongest win</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.product.retailer_product_id}>
                <td>
                  <span className="canonical-table-product">
                    <ProductThumb
                      imageUrl={row.product.image_url}
                      title={row.product.title}
                    />
                    <span>
                      <strong>{row.product.title}</strong>
                      <span>
                        {row.product.retailer_product_id} ·{" "}
                        {brandTypeLabels[row.product.brand_type]}
                      </span>
                    </span>
                  </span>
                </td>
                <td>
                  <strong>
                    {reportFootprintLabel(
                      row.product,
                      reportFootprintCountFor(row.product, retailerFootprints),
                    )}
                  </strong>
                  <span>
                    Store distribution counts exact product Search results with
                    price greater than zero.
                  </span>
                </td>
                <td>
                  <strong>{row.relationships.length.toLocaleString()}</strong>
                  <span>
                    {row.walmartLosses.toLocaleString()} losses ·{" "}
                    {row.walmartWins.toLocaleString()} wins ·{" "}
                    {row.parityOrUnscored.toLocaleString()} parity/unscored
                  </span>
                  <span>
                    {row.competitorRetailers.map(displayLabel).join(", ")}
                  </span>
                </td>
                <td>
                  {row.largestLoss ? (
                    <>
                      <strong>
                        Loss{" "}
                        {formatSignedCurrency(
                          row.largestLoss.comparison.price_delta,
                        )}
                      </strong>
                      <span>
                        vs.{" "}
                        {displayLabel(
                          row.largestLoss.competitor_product.retailer_id,
                        )}{" "}
                        ·{" "}
                        {formatPercent(
                          Math.abs(
                            row.largestLoss.comparison.price_delta_percent,
                          ),
                        )}
                      </span>
                    </>
                  ) : row.strongestWin ? (
                    <>
                      <strong>
                        Win{" "}
                        {formatSignedCurrency(
                          row.strongestWin.comparison.price_delta,
                        )}
                      </strong>
                      <span>
                        vs.{" "}
                        {displayLabel(
                          row.strongestWin.competitor_product.retailer_id,
                        )}{" "}
                        ·{" "}
                        {formatPercent(
                          Math.abs(
                            row.strongestWin.comparison.price_delta_percent,
                          ),
                        )}
                      </span>
                    </>
                  ) : (
                    <>
                      <strong>Parity / unscored</strong>
                      <span>No loss or win relationship in this row.</span>
                    </>
                  )}
                </td>
                <td>
                  <span className="canonical-table-actions">
                    <Link
                      href={productMonitoringHref(analysisId, row.product)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Map
                    </Link>
                    <button
                      type="button"
                      onClick={() =>
                        setSelectedEvidenceTarget(
                          productEvidenceTarget(
                            row.product,
                            "Walmart",
                            "Walmart store evidence",
                            retailerFootprints,
                          ),
                        )
                      }
                    >
                      Drawer
                    </button>
                    <Link
                      href={productEvidenceCsvHref(analysisId, row.product)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      CSV
                    </Link>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {selectedEvidenceTarget ? (
        <StoreEvidenceDrawer
          analysisId={analysisId}
          target={selectedEvidenceTarget}
          onClose={() => setSelectedEvidenceTarget(null)}
        />
      ) : null}
    </>
  );
}

function ProductThumb({
  imageUrl,
  title,
}: Readonly<{ imageUrl: string | null; title: string }>) {
  return (
    <span className="canonical-table-thumb">
      {imageUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={imageUrl} alt="" loading="lazy" />
      ) : (
        <b>{title.slice(0, 1)}</b>
      )}
    </span>
  );
}

function ProductLocationEvidencePanel({
  analysisId,
  footprint,
  retailerFootprints,
}: Readonly<{
  analysisId: string;
  footprint: ProductFootprint;
  retailerFootprints: Map<string, number>;
}>) {
  const [selectedEvidenceTarget, setSelectedEvidenceTarget] =
    useState<ProductEvidenceTarget | null>(null);
  const mapRequestPath = useMemo(
    () => mapEvidenceHref(analysisId, footprint.product, "summary"),
    [analysisId, footprint.product],
  );
  const [mapState, setMapState] = useState<{
    requestPath: string;
    data: PriceMonitoringMap | null;
    error: string | null;
  }>({
    requestPath: "",
    data: null,
    error: null,
  });

  useEffect(() => {
    const controller = new AbortController();
    fetch(mapRequestPath, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Map evidence returned ${response.status}`);
        }
        setMapState({
          requestPath: mapRequestPath,
          data: (await response.json()) as PriceMonitoringMap,
          error: null,
        });
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError")
          return;
        setMapState({
          requestPath: mapRequestPath,
          data: null,
          error:
            reason instanceof Error
              ? reason.message
              : "Map evidence could not be loaded.",
        });
      });
    return () => controller.abort();
  }, [mapRequestPath]);

  const displayedMapData =
    mapState.requestPath === mapRequestPath ? mapState.data : null;
  const displayedMapError =
    mapState.requestPath === mapRequestPath ? mapState.error : null;

  return (
    <div className="canonical-location-panel">
      <article className="canonical-location-product">
        <ProductThumb
          imageUrl={footprint.product.image_url}
          title={footprint.product.title}
        />
        <div>
          <span>Selected Walmart product</span>
          <strong>{footprint.product.title}</strong>
          <p>
            {footprint.product.retailer_product_id} ·{" "}
            {reportFootprintLabel(
              footprint.product,
              reportFootprintCountFor(footprint.product, retailerFootprints),
            )}{" "}
            · {brandTypeLabels[footprint.product.brand_type]}
          </p>
        </div>
        <button
          className="canonical-dataset-link"
          type="button"
          onClick={() =>
            setSelectedEvidenceTarget(
              productEvidenceTarget(
                footprint.product,
                "Walmart",
                "Walmart store evidence",
                retailerFootprints,
              ),
            )
          }
        >
          Store list drawer
        </button>
      </article>
      <ExactProductMap
        mapData={displayedMapData}
        mapError={displayedMapError}
        reportFootprintCount={reportFootprintCountFor(
          footprint.product,
          retailerFootprints,
        )}
      />
      {selectedEvidenceTarget ? (
        <StoreEvidenceDrawer
          analysisId={analysisId}
          target={selectedEvidenceTarget}
          onClose={() => setSelectedEvidenceTarget(null)}
        />
      ) : null}
    </div>
  );
}

function StoreEvidenceDrawer({
  analysisId,
  target,
  onClose,
}: Readonly<{
  analysisId: string;
  target: ProductEvidenceTarget;
  onClose: () => void;
}>) {
  const requestPath = useMemo(
    () => mapEvidenceHref(analysisId, target.product, "full"),
    [analysisId, target.product],
  );
  const [mapState, setMapState] = useState<{
    requestPath: string;
    data: PriceMonitoringMap | null;
    error: string | null;
  }>({
    requestPath: "",
    data: null,
    error: null,
  });

  useEffect(() => {
    const controller = new AbortController();
    fetch(requestPath, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Store evidence returned ${response.status}`);
        }
        setMapState({
          requestPath,
          data: (await response.json()) as PriceMonitoringMap,
          error: null,
        });
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError")
          return;
        setMapState({
          requestPath,
          data: null,
          error:
            reason instanceof Error
              ? reason.message
              : "Store evidence could not be loaded.",
        });
      });
    return () => controller.abort();
  }, [requestPath]);

  const mapData = mapState.requestPath === requestPath ? mapState.data : null;
  const error = mapState.requestPath === requestPath ? mapState.error : null;
  const [selectedState, setSelectedState] = useState("all");
  const rows = useMemo(() => storeEvidenceRows(mapData), [mapData]);
  const searchedRows = useMemo(() => searchedStoreRows(mapData), [mapData]);
  const stateOptions = useMemo(
    () => stateOptionsFromPoints(searchedRows),
    [searchedRows],
  );
  const activeState =
    selectedState === "all" || stateOptions.includes(selectedState)
      ? selectedState
      : "all";
  const filteredRows = useMemo(
    () =>
      activeState === "all"
        ? rows
        : rows.filter((point) => point.state === activeState),
    [rows, activeState],
  );
  const filteredSearchedRows = useMemo(
    () =>
      activeState === "all"
        ? searchedRows
        : searchedRows.filter((point) => point.state === activeState),
    [searchedRows, activeState],
  );
  const exportRows = useMemo(
    () => exportableStoreRows(filteredSearchedRows),
    [filteredSearchedRows],
  );
  const searchedStoreCount =
    searchedStoreCountFromMap(mapData) ??
    target.product.distribution.searched_store_count;
  const filteredSearchedStoreCount =
    activeState === "all" ? searchedStoreCount : filteredSearchedRows.length;
  const filteredObservedStoreCount =
    activeState === "all"
      ? (mapData?.display.distribution_store_count ??
        target.product.distribution.physical_store_distribution_count)
      : filteredRows.length;
  const observedStoreCount =
    mapData?.display.distribution_store_count ??
    target.product.distribution.physical_store_distribution_count;
  const notObservedStoreCount =
    searchedStoreCount === null
      ? null
      : Math.max(0, searchedStoreCount - observedStoreCount);
  const filteredNotObservedStoreCount =
    filteredSearchedStoreCount === null
      ? null
      : Math.max(0, filteredSearchedStoreCount - filteredObservedStoreCount);
  const searchedRowShare =
    searchedStoreCount && searchedStoreCount > 0
      ? observedStoreCount / searchedStoreCount
      : null;
  const reportFootprintShare =
    target.reportFootprintCount && target.reportFootprintCount > 0
      ? observedStoreCount / target.reportFootprintCount
      : null;
  const filteredReportFootprintShare =
    target.reportFootprintCount && target.reportFootprintCount > 0
      ? filteredObservedStoreCount / target.reportFootprintCount
      : null;
  const fileStem = safeDownloadName(
    `${target.product.retailer_id}-${target.product.retailer_product_id}-store-evidence`,
  );

  const downloadCsv = () => {
    downloadTextFile(`${fileStem}.csv`, rowsToCsv(exportRows), "text/csv");
  };

  const downloadJson = () => {
    downloadTextFile(
      `${fileStem}.json`,
      JSON.stringify(
        {
          analysis_id: analysisId,
          retailer: target.product.retailer_id,
          product_id: target.product.retailer_product_id,
          distribution_contract: mapData?.distribution_contract ?? null,
          display: mapData?.display ?? null,
          report_footprint_store_count: target.reportFootprintCount ?? null,
          report_footprint_share: reportFootprintShare,
          searched_store_count: searchedStoreCount,
          observed_distribution_store_count: observedStoreCount,
          not_observed_searched_store_count: notObservedStoreCount,
          visible_observed_distribution_store_count: filteredObservedStoreCount,
          visible_not_observed_searched_store_count:
            filteredNotObservedStoreCount,
          searched_row_share: searchedRowShare,
          store_share: searchedRowShare,
          state_filter: activeState === "all" ? null : activeState,
          rows: exportRows,
        },
        null,
        2,
      ),
      "application/json",
    );
  };

  const downloadExcel = () => {
    const columns = Object.keys(
      exportRows[0] ?? {
        scope_key: "",
        store_number: "",
        store_name: "",
        distribution_store_id: "",
        city: "",
        state: "",
        zipcode: "",
        country: "",
        latitude: "",
        longitude: "",
        search_price: "",
        difference_from_reference: "",
        search_observed: "",
        is_sponsored: "",
      },
    );
    const worksheetRows = [
      columns,
      ...exportRows.map((row) =>
        columns.map((column) => row[column as keyof typeof row] ?? ""),
      ),
    ];
    const xml = `<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
<Worksheet ss:Name="Store evidence">
<Table>
${worksheetRows
  .map(
    (row) =>
      `<Row>${row
        .map(
          (value) =>
            `<Cell><Data ss:Type="${
              typeof value === "number" ? "Number" : "String"
            }">${escapeXml(value)}</Data></Cell>`,
        )
        .join("")}</Row>`,
  )
  .join("\n")}
</Table>
</Worksheet>
</Workbook>`;
    downloadTextFile(`${fileStem}.xls`, xml, "application/vnd.ms-excel");
  };

  return (
    <div className="pm-drawer-layer canonical-store-drawer-layer">
      <button
        aria-label="Close store evidence"
        className="pm-drawer-backdrop"
        onClick={onClose}
        type="button"
      />
      <aside
        className="pm-product-drawer canonical-store-drawer"
        role="dialog"
        aria-modal="true"
      >
        <header>
          <div className="pm-product-identity">
            {target.product.image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={target.product.image_url} alt="" loading="lazy" />
            ) : (
              <span>{target.product.title.slice(0, 1)}</span>
            )}
            <div>
              <p className="section-kicker">{target.roleLabel}</p>
              <h2>{target.product.title}</h2>
              <small>
                {target.retailerLabel} · {target.product.retailer_product_id} ·{" "}
                {reportFootprintLabel(
                  target.product,
                  target.reportFootprintCount,
                )}
              </small>
            </div>
          </div>
          <button
            aria-label="Close store evidence"
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </header>
        <section className="pm-drawer-metrics canonical-store-drawer-metrics">
          <div>
            <span>Distribution stores</span>
            <strong>
              {target.product.distribution.physical_store_distribution_count.toLocaleString()}
            </strong>
          </div>
          <div>
            <span>Report footprint share</span>
            <strong>
              {reportFootprintShare === null
                ? "Unavailable"
                : formatPercent(reportFootprintShare)}
            </strong>
          </div>
          <div>
            <span>Searched rows returned</span>
            <strong>
              {searchedStoreCount?.toLocaleString() ?? "Loading…"}
            </strong>
          </div>
          <div>
            <span>Service areas</span>
            <strong>
              {target.product.distribution.service_area_presence_count.toLocaleString()}
            </strong>
          </div>
          <div>
            <span>Visible stores</span>
            <strong>
              {mapData
                ? filteredObservedStoreCount.toLocaleString()
                : "Loading…"}
            </strong>
          </div>
        </section>
        <section className="pm-drawer-section">
          <header>
            <div>
              <h3>Store list detail</h3>
              <p>
                Store rows are exact product store-level Search observations
                with price greater than zero. This is distribution evidence, not
                an in-stock claim. Downloads include observed distribution rows
                and returned searched stores where this product was not
                observed. Report footprint share uses the retailer denominator
                shown in the current report, and searched-row share remains an
                audit field.
              </p>
            </div>
            <div className="canonical-drawer-export-actions">
              <label className="canonical-state-filter">
                <span>State</span>
                <select
                  disabled={!stateOptions.length}
                  value={activeState}
                  onChange={(event) => setSelectedState(event.target.value)}
                >
                  <option value="all">All states</option>
                  {stateOptions.map((state) => (
                    <option key={state} value={state}>
                      {state}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="canonical-dataset-link"
                disabled={!mapData}
                onClick={downloadCsv}
                type="button"
              >
                CSV
              </button>
              <button
                className="canonical-dataset-link"
                disabled={!mapData}
                onClick={downloadExcel}
                type="button"
              >
                Excel
              </button>
              <button
                className="canonical-dataset-link"
                disabled={!mapData}
                onClick={downloadJson}
                type="button"
              >
                JSON
              </button>
            </div>
          </header>
          {error ? <p className="empty-note">{error}</p> : null}
          {!mapData && !error ? (
            <p className="empty-note">Loading full store evidence…</p>
          ) : null}
          {mapData ? (
            <>
              <div className="canonical-store-drawer-summary">
                <span>
                  {filteredObservedStoreCount.toLocaleString()} visible observed
                  distribution stores
                  {activeState === "all" ? "" : ` in ${activeState}`}
                  {target.reportFootprintCount &&
                  filteredReportFootprintShare !== null
                    ? ` · ${formatPercent(
                        filteredReportFootprintShare,
                      )} of ${target.reportFootprintCount.toLocaleString()} ${target.retailerLabel} report footprint stores`
                    : " · report-footprint denominator unavailable"}
                </span>
                <span>
                  {filteredRows.length.toLocaleString()} returned observed store
                  rows ·{" "}
                  {filteredSearchedStoreCount !== null
                    ? `${filteredSearchedStoreCount.toLocaleString()} returned searched store rows`
                    : "returned searched-row denominator unavailable"}
                  {activeState === "all" && searchedRowShare !== null
                    ? ` · ${formatPercent(searchedRowShare)} searched-row share`
                    : ""}
                </span>
                {filteredNotObservedStoreCount !== null ? (
                  <span>
                    {filteredNotObservedStoreCount.toLocaleString()} returned
                    searched stores
                    {activeState === "all" ? "" : ` in ${activeState}`} did not
                    return this exact product in positive-price Search.
                  </span>
                ) : null}
                {mapData.display.observed_sampled ? (
                  <span>
                    Full-detail API returned a deterministic sample; downloads
                    use the returned drawer rows.
                  </span>
                ) : null}
              </div>
              <MappedLocationTable
                points={filteredRows}
                title="Store list"
                wrapClassName="canonical-store-drawer-table"
              />
            </>
          ) : null}
        </section>
        <footer>
          <p>
            Distribution is based only on positive-price store-level Search
            presence for the exact retailer product ID. Service areas remain
            separately labeled.
          </p>
        </footer>
      </aside>
    </div>
  );
}

const statesTopology = statesTopologySource as Topology;
const continentalStateFeatures = (
  feature(
    statesTopology,
    statesTopology.objects.states as GeometryCollection,
  ) as unknown as {
    features: StateFeature[];
  }
).features;

function projectCoordinate(longitude: number, latitude: number) {
  return {
    x: ((longitude + 125) / 59) * 900 + 30,
    y: ((50 - latitude) / 26) * 460 + 30,
  };
}

function coordinateRingPath(value: unknown) {
  if (!Array.isArray(value)) return "";
  const points = value.filter(
    (item): item is [number, number] =>
      Array.isArray(item) &&
      typeof item[0] === "number" &&
      typeof item[1] === "number",
  );
  if (points.length === 0) return "";
  return `${points
    .map(([longitude, latitude], index) => {
      const { x, y } = projectCoordinate(longitude, latitude);
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ")} Z`;
}

function geometryPath(geometry: { type: string; coordinates: unknown }) {
  if (!Array.isArray(geometry.coordinates)) return "";
  const polygons =
    geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  return polygons
    .flatMap((polygon) => (Array.isArray(polygon) ? polygon : []))
    .map(coordinateRingPath)
    .filter(Boolean)
    .join(" ");
}

function pointClass(point: PriceMonitoringMapPoint) {
  if (point.status === "not_observed") return "not-observed";
  const difference = point.difference_from_reference ?? 0;
  if (difference < -0.005) return "price-lower";
  if (difference > 0.005) return "price-higher";
  return "price-parity";
}

function ExactProductMap({
  mapData,
  mapError,
  reportFootprintCount,
}: Readonly<{
  mapData: PriceMonitoringMap | null;
  mapError: string | null;
  reportFootprintCount: number | null;
}>) {
  const [selectedState, setSelectedState] = useState("all");
  const searchedStoreCount = searchedStoreCountFromMap(mapData);
  const searchedRowShare =
    mapData && searchedStoreCount
      ? mapData.display.distribution_store_count / searchedStoreCount
      : null;
  const reportFootprintShare =
    mapData && reportFootprintCount
      ? mapData.display.distribution_store_count / reportFootprintCount
      : null;
  const stateOptions = useMemo(
    () => stateOptionsFromPoints(mapData?.points ?? []),
    [mapData],
  );
  const activeState =
    selectedState === "all" || stateOptions.includes(selectedState)
      ? selectedState
      : "all";
  const visiblePoints = useMemo(
    () =>
      (mapData?.points ?? [])
        .filter(
          (point) =>
            point.status === "observed" &&
            (activeState === "all" || point.state === activeState) &&
            Number.isFinite(point.latitude) &&
            Number.isFinite(point.longitude) &&
            point.latitude >= 24 &&
            point.latitude <= 50 &&
            point.longitude >= -125 &&
            point.longitude <= -66,
        )
        .slice(0, 700),
    [activeState, mapData],
  );
  return (
    <>
      <div className="canonical-map-card">
        <svg
          viewBox="0 0 960 520"
          role="img"
          aria-label="Exact Walmart product positive-price store distribution map"
        >
          <rect width="960" height="520" rx="22" />
          <g className="canonical-state-layer">
            {continentalStateFeatures.map((state) => (
              <path d={geometryPath(state.geometry)} key={String(state.id)} />
            ))}
          </g>
          <g className="canonical-map-point-layer">
            {visiblePoints.map((point) => {
              const projected = projectCoordinate(
                point.longitude,
                point.latitude,
              );
              const location = [
                point.store_name,
                point.city,
                point.state,
                point.zipcode,
              ]
                .filter(Boolean)
                .join(" · ");
              return (
                <circle
                  className={pointClass(point)}
                  cx={projected.x}
                  cy={projected.y}
                  key={point.scope_key}
                  r={2.6}
                >
                  <title>
                    {location || point.scope_key} ·{" "}
                    {point.price === null
                      ? "price unavailable"
                      : formatCurrency(point.price)}
                  </title>
                </circle>
              );
            })}
          </g>
          {!mapData && !mapError ? (
            <text
              className="canonical-map-status"
              x="480"
              y="490"
              textAnchor="middle"
            >
              Loading exact-product locations…
            </text>
          ) : null}
        </svg>
        <aside>
          <span>Source-backed location evidence</span>
          <strong>
            {mapData
              ? reportFootprintCount
                ? `${mapData.display.distribution_store_count.toLocaleString()} stores (${formatPercent(
                    reportFootprintShare ?? 0,
                  )} of ${reportFootprintCount.toLocaleString()} report footprint)`
                : `${mapData.display.distribution_store_count.toLocaleString()} stores`
              : mapError
                ? "Unavailable"
                : "Loading…"}
          </strong>
          <p>
            {mapData
              ? `${
                  searchedStoreCount && searchedRowShare !== null
                    ? `${searchedStoreCount.toLocaleString()} returned searched store rows; ${formatPercent(
                        searchedRowShare,
                      )} searched-row share.`
                    : "Returned searched-row denominator unavailable."
                } ${mapData.display.service_area_presence_count.toLocaleString()} service-area presences tracked separately.`
              : (mapError ??
                "Fetching exact product map evidence from the report API.")}
          </p>
          <div className="canonical-map-legend">
            <span className="price-lower">Below footprint median</span>
            <span className="price-parity">At median</span>
            <span className="price-higher">Above median</span>
          </div>
          {stateOptions.length ? (
            <label className="canonical-state-filter canonical-map-state-filter">
              <span>State</span>
              <select
                value={activeState}
                onChange={(event) => setSelectedState(event.target.value)}
              >
                <option value="all">All states</option>
                {stateOptions.map((state) => (
                  <option key={state} value={state}>
                    {state}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {mapData?.display.observed_sampled ? (
            <small>
              Map displays a deterministic sample; the store count uses the full
              source-backed distribution set.
            </small>
          ) : null}
        </aside>
      </div>
      {mapData ? (
        <MappedLocationTable
          points={visiblePoints.slice(0, 12)}
          title="Mapped preview"
        />
      ) : null}
    </>
  );
}

function MappedLocationTable({
  points,
  title = "Store list",
  wrapClassName = "",
}: Readonly<{
  points: PriceMonitoringMapPoint[];
  title?: string;
  wrapClassName?: string;
}>) {
  if (!points.length) {
    return (
      <p className="empty-note">
        No mappable positive-price store locations were returned for this
        product.
      </p>
    );
  }
  return (
    <div className={`canonical-table-wrap ${wrapClassName}`.trim()}>
      <table className="canonical-insight-table canonical-location-table">
        <thead>
          <tr>
            <th>{title}</th>
            <th>City</th>
            <th>State</th>
            <th>ZIP</th>
            <th>Search price</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point) => (
            <tr key={point.scope_key}>
              <td>
                <strong>{point.store_name ?? "Store"}</strong>
                <span>
                  {point.store_number
                    ? `Store ${point.store_number}`
                    : point.distribution_store_id}
                </span>
              </td>
              <td>
                <strong>{point.city ?? "Unknown"}</strong>
              </td>
              <td>
                <strong>{point.state ?? "Unknown"}</strong>
              </td>
              <td>
                <strong>{point.zipcode ?? "Unknown"}</strong>
              </td>
              <td>
                <strong>
                  {point.price === null
                    ? "Unavailable"
                    : formatCurrency(point.price)}
                </strong>
                <span>positive-price Search result</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PriceArchitecture({
  analysisId,
  relationships,
  brandGroups,
  retailerFootprints,
}: Readonly<{
  analysisId: string;
  relationships: ProductRelationship[];
  brandGroups: Array<{
    brandType: BrandType;
    relationships: ProductRelationship[];
  }>;
  retailerFootprints: Map<string, number>;
}>) {
  return (
    <>
      <section className="workspace-section">
        <header>
          <div>
            <h2>Price ladder</h2>
            <p>
              Each row is one governed product relationship with the exact
              displayed unit basis, Walmart comparison value, competitor
              comparison value, and signed gap. Normalized values are labeled so
              they are not confused with shelf/package prices.
            </p>
          </div>
        </header>
        <PriceArchitectureTable
          analysisId={analysisId}
          relationships={relationships}
          retailerFootprints={retailerFootprints}
        />
      </section>
      {brandGroups
        .filter(({ relationships }) => relationships.length > 0)
        .map(({ brandType, relationships }) => (
          <section className="workspace-section" key={brandType}>
            <header>
              <div>
                <h2>
                  {brandTypeLabels[brandType]} price role (
                  {relationships.length.toLocaleString()})
                </h2>
                <p>
                  {brandType === "regional"
                    ? "Fact-only regional section: counts and governed price relationships only."
                    : "Factual brand-role slice of governed relationships, using the same reporting prices as the table above."}
                </p>
              </div>
            </header>
            <PriceArchitectureTable
              analysisId={analysisId}
              relationships={relationships}
              retailerFootprints={retailerFootprints}
            />
          </section>
        ))}
    </>
  );
}

function PriceArchitectureTable({
  analysisId,
  relationships,
  retailerFootprints,
}: Readonly<{
  analysisId: string;
  relationships: ProductRelationship[];
  retailerFootprints: Map<string, number>;
}>) {
  const [selectedEvidenceTarget, setSelectedEvidenceTarget] =
    useState<ProductEvidenceTarget | null>(null);
  const rows = [...relationships].sort(
    (left, right) =>
      left.benchmark_product.brand_type.localeCompare(
        right.benchmark_product.brand_type,
      ) ||
      right.benchmark_product.distribution.physical_store_distribution_count -
        left.benchmark_product.distribution.physical_store_distribution_count ||
      Math.abs(right.comparison.price_delta_percent) -
        Math.abs(left.comparison.price_delta_percent),
  );
  if (!rows.length) {
    return <p className="empty-note">No governed relationships available.</p>;
  }
  return (
    <div className="canonical-table-wrap">
      <table className="canonical-insight-table canonical-price-table">
        <thead>
          <tr>
            <th>Walmart product</th>
            <th>Competitor product</th>
            <th>Brand role</th>
            <th>Walmart</th>
            <th>Competitor</th>
            <th>Store footprint</th>
            <th>Gap</th>
            <th>Outcome</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((relationship) => (
            <tr key={relationship.relationship_id}>
              <td>
                <strong>{relationship.benchmark_product.title}</strong>
                <span>{relationship.benchmark_product.package.label}</span>
              </td>
              <td>
                <strong>{relationship.competitor_product.title}</strong>
                <span>
                  {displayLabel(relationship.competitor_product.retailer_id)} ·{" "}
                  {relationship.competitor_product.package.label}
                </span>
              </td>
              <td>
                <strong>
                  {brandTypeLabels[relationship.benchmark_product.brand_type]}
                </strong>
                <span>{relationship.comparison.unit_basis}</span>
              </td>
              <td>
                <strong>
                  {priceDisplay(relationship.benchmark_product).primary}
                </strong>
                <span>
                  {priceDisplay(relationship.benchmark_product).secondary}
                </span>
                <span>
                  {priceBasisLabel(
                    canonicalRelationshipPriceBasis(relationship),
                  )}{" "}
                  · {relationship.comparison.comparison_basis}
                </span>
              </td>
              <td>
                <strong>
                  {priceDisplay(relationship.competitor_product).primary}
                </strong>
                <span>
                  {relationship.competitor_product.retailer_product_id}
                </span>
                <span>
                  {priceDisplay(relationship.competitor_product).secondary}
                </span>
              </td>
              <td>
                <strong>
                  WMT{" "}
                  {reportFootprintLabel(
                    relationship.benchmark_product,
                    reportFootprintCountFor(
                      relationship.benchmark_product,
                      retailerFootprints,
                    ),
                  )}
                </strong>
                <span>
                  {displayLabel(relationship.competitor_product.retailer_id)}{" "}
                  {reportFootprintLabel(
                    relationship.competitor_product,
                    reportFootprintCountFor(
                      relationship.competitor_product,
                      retailerFootprints,
                    ),
                  )}
                </span>
                <span className="canonical-table-actions">
                  <button
                    type="button"
                    onClick={() =>
                      setSelectedEvidenceTarget(
                        productEvidenceTarget(
                          relationship.benchmark_product,
                          "Walmart",
                          "Walmart store evidence",
                          retailerFootprints,
                        ),
                      )
                    }
                  >
                    WMT stores
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setSelectedEvidenceTarget(
                        productEvidenceTarget(
                          relationship.competitor_product,
                          displayLabel(
                            relationship.competitor_product.retailer_id,
                          ),
                          "Competitor store evidence",
                          retailerFootprints,
                        ),
                      )
                    }
                  >
                    Comp stores
                  </button>
                </span>
              </td>
              <td>
                <span className="canonical-gap-cell">
                  <strong>
                    {formatSignedCurrency(relationship.comparison.price_delta)}
                  </strong>
                  <span>
                    {formatPercent(
                      Math.abs(relationship.comparison.price_delta_percent),
                    )}
                  </span>
                </span>
              </td>
              <td>
                <span
                  className={`canonical-outcome-pill ${relationship.comparison.outcome}`}
                >
                  {outcomeLabels[relationship.comparison.outcome]}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {selectedEvidenceTarget ? (
        <StoreEvidenceDrawer
          analysisId={analysisId}
          target={selectedEvidenceTarget}
          onClose={() => setSelectedEvidenceTarget(null)}
        />
      ) : null}
    </div>
  );
}

function EvidenceQa({
  dataset,
  integrityIssues,
}: Readonly<{
  dataset: CanonicalDataset;
  integrityIssues: ReturnType<typeof canonicalReportIntegrityIssues>;
}>) {
  const checklist = canonicalReportChecklist(dataset);
  return (
    <>
      <section className="workspace-section">
        <header>
          <div>
            <h2>Evidence and guardrails</h2>
            <p>
              These are the controls that keep the report from looking precise
              while quietly mixing invalid prices, third-party seller products,
              or distribution definitions.
            </p>
          </div>
        </header>
        <div className="metric-grid canonical-metric-grid">
          <Metric
            label="Included"
            value={dataset.qa.included_relationship_count}
          />
          <Metric
            label="Excluded"
            value={dataset.qa.excluded_relationship_count}
          />
          <Metric
            label="Invalid price records"
            value={dataset.qa.invalid_price_record_count}
          />
          <Metric
            label="Unverified seller products"
            value={dataset.qa.unverified_seller_product_count}
          />
        </div>
        <div className="canonical-evidence-grid">
          <article>
            <h3>Distribution contract</h3>
            <p>
              {displayLabel(dataset.contracts.distribution.basis)} ·{" "}
              {displayLabel(dataset.contracts.distribution.price_rule)} · no
              stock status or sponsorship signal used.
            </p>
          </article>
          <article>
            <h3>Price normalization</h3>
            <p>
              {dataset.price_normalization.unit_basis}; zero regular or
              discounted price means missing, not free.
            </p>
          </article>
          <article>
            <h3>Seller governance</h3>
            <p>
              Benchmark products must have a qualified seller or an explicit
              not-applicable status.
            </p>
          </article>
        </div>
        <div className="canonical-checklist" aria-label="Validation checklist">
          {integrityIssues.length ? (
            <article className="blocked">
              <span>Blocked</span>
              <strong>Dataset integrity</strong>
              <p>
                {integrityIssues.length.toLocaleString()} integrity issue
                {integrityIssues.length === 1 ? "" : "s"} must be resolved
                before export or publication. First issue:{" "}
                {displayLabel(integrityIssues[0]!.code)}.
              </p>
            </article>
          ) : null}
          {checklist.map((item) => (
            <article className={item.status} key={item.id}>
              <span>{displayLabel(item.status)}</span>
              <strong>{item.label}</strong>
              <p>{item.detail}</p>
            </article>
          ))}
        </div>
      </section>
      <section className="workspace-section">
        <header>
          <div>
            <h2>Excluded relationships</h2>
            <p>
              Exclusions are intentionally visible so missing/invalid evidence
              does not disappear into a rollup.
            </p>
          </div>
        </header>
        {dataset.excluded_relationships.length ? (
          <div className="canonical-exclusion-list">
            {dataset.excluded_relationships.map((row) => (
              <article key={row.relationship_id}>
                <span>{displayLabel(row.reason_code)}</span>
                <strong>
                  {row.benchmark_product_id} vs. {row.competitor_product_id}
                </strong>
                <p>{row.reason}</p>
              </article>
            ))}
          </div>
        ) : (
          <p className="empty-note">
            No relationships were excluded by the canonical guardrails.
          </p>
        )}
      </section>
    </>
  );
}

function RelationshipSection({
  analysisId,
  title,
  note,
  relationships,
  retailerFootprints,
}: Readonly<{
  analysisId: string;
  title: string;
  note: string;
  relationships: ProductRelationship[];
  retailerFootprints: Map<string, number>;
}>) {
  const [selectedEvidenceTarget, setSelectedEvidenceTarget] =
    useState<ProductEvidenceTarget | null>(null);
  return (
    <>
      <section className="workspace-section">
        <header>
          <div>
            <h2>{title}</h2>
            <p>{note}</p>
          </div>
        </header>
        {relationships.length ? (
          <div className="canonical-product-grid">
            {relationships.map((relationship) => (
              <RelationshipCard
                key={relationship.relationship_id}
                onSelectEvidenceTarget={setSelectedEvidenceTarget}
                relationship={relationship}
                retailerFootprints={retailerFootprints}
              />
            ))}
          </div>
        ) : (
          <p className="empty-note">
            No included relationships in this section.
          </p>
        )}
      </section>
      {selectedEvidenceTarget ? (
        <StoreEvidenceDrawer
          analysisId={analysisId}
          target={selectedEvidenceTarget}
          onClose={() => setSelectedEvidenceTarget(null)}
        />
      ) : null}
    </>
  );
}

function RelationshipCard({
  onSelectEvidenceTarget,
  relationship,
  retailerFootprints,
}: Readonly<{
  onSelectEvidenceTarget: (target: ProductEvidenceTarget) => void;
  relationship: ProductRelationship;
  retailerFootprints: Map<string, number>;
}>) {
  const benchmarkHref = productHref(relationship.benchmark_product.url);
  const competitorHref = productHref(relationship.competitor_product.url);
  const delta = relationship.comparison.price_delta;
  const deltaLabel =
    delta >= 0
      ? `${formatCurrency(delta)} above competitor`
      : `${formatCurrency(Math.abs(delta))} below competitor`;
  const deltaExplanation = `Walmart comparison value is ${deltaLabel} on the normalized/reporting basis; it is not a shelf/package price unless a source-backed package price is shown.`;
  return (
    <article
      className={`canonical-product-card ${relationship.comparison.outcome}`}
    >
      <div className="canonical-product-pair">
        <ProductTile
          href={benchmarkHref}
          title={relationship.benchmark_product.title}
          imageUrl={relationship.benchmark_product.image_url}
          retailer="Walmart"
          price={priceDisplay(relationship.benchmark_product)}
          distribution={reportFootprintLabel(
            relationship.benchmark_product,
            reportFootprintCountFor(
              relationship.benchmark_product,
              retailerFootprints,
            ),
          )}
        />
        <span className="canonical-versus">vs</span>
        <ProductTile
          href={competitorHref}
          title={relationship.competitor_product.title}
          imageUrl={relationship.competitor_product.image_url}
          retailer={displayLabel(relationship.competitor_product.retailer_id)}
          price={priceDisplay(relationship.competitor_product)}
          distribution={reportFootprintLabel(
            relationship.competitor_product,
            reportFootprintCountFor(
              relationship.competitor_product,
              retailerFootprints,
            ),
          )}
        />
      </div>
      <div className="canonical-product-card-footer">
        <span>{outcomeLabels[relationship.comparison.outcome]}</span>
        <strong>{deltaLabel}</strong>
        <p>
          {formatPercent(Math.abs(relationship.comparison.price_delta_percent))}{" "}
          gap · {displayLabel(relationship.benchmark_product.brand_type)} ·{" "}
          {relationship.comparison.match_certification.status.replaceAll(
            "_",
            " ",
          )}
        </p>
        <small>{deltaExplanation}</small>
        <div className="canonical-product-card-actions">
          <button
            type="button"
            onClick={() =>
              onSelectEvidenceTarget(
                productEvidenceTarget(
                  relationship.benchmark_product,
                  "Walmart",
                  "Walmart store evidence",
                  retailerFootprints,
                ),
              )
            }
          >
            Walmart store list
          </button>
          <button
            type="button"
            onClick={() =>
              onSelectEvidenceTarget(
                productEvidenceTarget(
                  relationship.competitor_product,
                  displayLabel(relationship.competitor_product.retailer_id),
                  "Competitor store evidence",
                  retailerFootprints,
                ),
              )
            }
          >
            Competitor store list
          </button>
        </div>
      </div>
    </article>
  );
}

function ProductTile({
  href,
  title,
  imageUrl,
  retailer,
  price,
  distribution,
}: Readonly<{
  href: string | null;
  title: string;
  imageUrl: string | null;
  retailer: string;
  price: ReturnType<typeof priceDisplay>;
  distribution: string;
}>) {
  const body = (
    <>
      <span className="canonical-product-image">
        {imageUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={imageUrl} alt="" loading="lazy" />
        ) : (
          <b>{title.slice(0, 1)}</b>
        )}
      </span>
      <span className="canonical-product-detail">
        <i>{retailer}</i>
        <strong>{title}</strong>
        <em>{price.primary}</em>
        <small className="canonical-price-note">{price.secondary}</small>
        <small>{distribution}</small>
      </span>
    </>
  );
  return href ? (
    <Link
      href={href}
      className="canonical-product-tile"
      target="_blank"
      rel="noreferrer"
    >
      {body}
    </Link>
  ) : (
    <span className="canonical-product-tile">{body}</span>
  );
}

function Metric({ label, value }: Readonly<{ label: string; value: number }>) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{value.toLocaleString()}</strong>
    </div>
  );
}
