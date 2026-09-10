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
  canonicalCompetitorOptions,
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
type BrandType = ProductRelationship["benchmark_product"]["brand_type"];
type PriceMonitoringMapPoint = PriceMonitoringMap["points"][number];
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

function distributionLabel(
  distribution: ProductRelationship["benchmark_product"]["distribution"],
) {
  return `${distribution.physical_store_distribution_count.toLocaleString()} positive-price stores`;
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
  product: BenchmarkProduct,
  tab = "overview",
) {
  const parameters = new URLSearchParams({
    retailer: product.retailer_id,
    product_id: product.retailer_product_id,
    tab,
  });
  return `/price-monitoring/${encodeURIComponent(analysisId)}?${parameters.toString()}`;
}

function productEvidenceCsvHref(analysisId: string, product: BenchmarkProduct) {
  const parameters = new URLSearchParams({
    retailer: product.retailer_id,
    product_id: product.retailer_product_id,
  });
  return `/api/price-monitoring/${encodeURIComponent(analysisId)}/evidence.csv?${parameters.toString()}`;
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
            dataset={dataset}
            groups={groups}
            brandTypeSummary={brandTypeSummary}
          />
        ) : null}
        {activeTab === "Product Wins & Losses" ? (
          <ProductWinsLosses dataset={dataset} />
        ) : null}
        {activeTab === "Distribution & Assortment" ? (
          <DistributionAssortment
            analysisId={analysis.analysis_id}
            relationships={broadWalmartRelationships}
            productFootprints={productFootprints.filter(
              (row) =>
                row.product.distribution.physical_store_distribution_count >=
                BROAD_WALMART_DISTRIBUTION_THRESHOLD,
            )}
            totalRelationships={dataset.product_relationships.length}
          />
        ) : null}
        {activeTab === "Price Architecture" ? (
          <PriceArchitecture
            brandGroups={brandGroups}
            relationships={dataset.product_relationships}
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
  dataset,
  groups,
  brandTypeSummary,
}: Readonly<{
  dataset: CanonicalDataset;
  groups: ReturnType<typeof relationshipGroups>;
  brandTypeSummary: ReturnType<typeof summarizeCanonicalBrandTypes>;
}>) {
  const topLosses = [...groups.walmartLosses]
    .sort(
      (left, right) =>
        right.benchmark_product.distribution.physical_store_distribution_count -
          left.benchmark_product.distribution
            .physical_store_distribution_count ||
        Math.abs(right.comparison.price_delta_percent) -
          Math.abs(left.comparison.price_delta_percent) ||
        left.benchmark_product.title.localeCompare(
          right.benchmark_product.title,
        ),
    )
    .slice(0, 8);
  const broadLosses = groups.walmartLosses.filter(
    (relationship) =>
      relationship.benchmark_product.distribution
        .physical_store_distribution_count >=
      BROAD_WALMART_DISTRIBUTION_THRESHOLD,
  );
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
            <h2>Highest-priority losses</h2>
            <p>
              This is the executive triage list, not a gallery. Rows prioritize
              Walmart losses with broad product footprints, large normalized
              price gaps, and inspectable match evidence.
            </p>
          </div>
          <span className="canonical-section-stat">
            {broadLosses.length.toLocaleString()} broad-footprint losses
          </span>
        </header>
        <ExecutivePriorityTable relationships={topLosses} />
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
  relationships,
}: Readonly<{ relationships: ProductRelationship[] }>) {
  if (!relationships.length) {
    return (
      <p className="empty-note">
        No Walmart losses are available in the governed relationship set.
      </p>
    );
  }
  return (
    <div className="canonical-table-wrap">
      <table className="canonical-insight-table">
        <thead>
          <tr>
            <th>Walmart product</th>
            <th>Competitor lower</th>
            <th>Gap</th>
            <th>Footprint</th>
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
              </td>
              <td>
                <strong>{relationship.competitor_product.title}</strong>
                <span>
                  {displayLabel(relationship.competitor_product.retailer_id)} ·{" "}
                  {relationship.competitor_product.price.reporting_price_label}
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
                  competitor advantage
                </span>
              </td>
              <td>
                <strong>
                  {relationship.benchmark_product.distribution.physical_store_distribution_count.toLocaleString()}
                </strong>
                <span>positive-price stores</span>
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
  );
}

function ProductWinsLosses({
  dataset,
}: Readonly<{ dataset: CanonicalDataset }>) {
  const [filters, setFilters] = useState<CanonicalRelationshipFilters>(
    DEFAULT_CANONICAL_RELATIONSHIP_FILTERS,
  );
  const competitorOptions = useMemo(
    () => canonicalCompetitorOptions(dataset.product_relationships),
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

  return (
    <>
      <section className="workspace-section canonical-browser-section">
        <header>
          <div>
            <h2>Product action board</h2>
            <p>
              Default view includes every governed relationship. Use filters to
              focus the same image cards by outcome, brand type, competitor,
              distribution footprint, or product text.
            </p>
          </div>
          <button
            type="button"
            className="text-link"
            onClick={() => setFilters(DEFAULT_CANONICAL_RELATIONSHIP_FILTERS)}
          >
            Reset filters
          </button>
        </header>
        <div className="canonical-filter-grid">
          <label>
            <span>Search products</span>
            <input
              type="search"
              value={filters.query}
              placeholder="Name, brand, product ID…"
              onChange={(event) => updateFilters({ query: event.target.value })}
            />
          </label>
          <label>
            <span>Outcome</span>
            <select
              value={filters.outcome}
              onChange={(event) =>
                updateFilters({
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
            <span>Walmart brand type</span>
            <select
              value={filters.brandType}
              onChange={(event) =>
                updateFilters({
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
            <span>Competitor</span>
            <select
              value={filters.competitorRetailerId}
              onChange={(event) =>
                updateFilters({ competitorRetailerId: event.target.value })
              }
            >
              <option value="all">All competitors</option>
              {competitorOptions.map((competitor) => (
                <option key={competitor} value={competitor}>
                  {displayLabel(competitor)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Walmart footprint</span>
            <select
              value={filters.minimumWalmartDistribution}
              onChange={(event) =>
                updateFilters({
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
                updateFilters({
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
        <p className="canonical-browser-summary">
          Showing {filteredRelationships.length.toLocaleString()} of{" "}
          {dataset.product_relationships.length.toLocaleString()} included
          relationships · {groups.walmartLosses.length.toLocaleString()} losses
          · {groups.walmartWins.length.toLocaleString()} wins ·{" "}
          {groups.parity.length.toLocaleString()} parity/unscored
        </p>
      </section>
      <RelationshipSection
        title={`All Walmart losses (${groups.walmartLosses.length.toLocaleString()})`}
        note="These are all included competitor-win relationships, not illustrative examples."
        relationships={groups.walmartLosses}
      />
      <RelationshipSection
        title={`All Walmart wins (${groups.walmartWins.length.toLocaleString()})`}
        note="These are all included Walmart-win relationships, not illustrative examples."
        relationships={groups.walmartWins}
      />
      <RelationshipSection
        title={`Parity / unscored (${groups.parity.length.toLocaleString()})`}
        note="Shown separately so parity does not dilute the action list."
        relationships={groups.parity}
      />
    </>
  );
}

function DistributionAssortment({
  analysisId,
  relationships,
  productFootprints,
  totalRelationships,
}: Readonly<{
  analysisId: string;
  relationships: ProductRelationship[];
  productFootprints: ProductFootprint[];
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
            <strong>{productFootprints.length.toLocaleString()}</strong>
            <p>
              Walmart products with at least 1,000 positive-price stores across{" "}
              {relationships.length.toLocaleString()} included relationships.
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
              Select a Walmart product to load its source-backed location
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
                    {row.product.distribution.physical_store_distribution_count.toLocaleString()}{" "}
                    stores
                  </option>
                ))}
              </select>
            </label>
            {selectedFootprint ? (
              <ProductLocationEvidencePanel
                analysisId={analysisId}
                footprint={selectedFootprint}
              />
            ) : null}
          </>
        ) : (
          <p className="empty-note">
            No Walmart products meet the broad-footprint threshold in this
            governed relationship set.
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
          rows={productFootprints}
        />
      </section>
    </>
  );
}

function ProductFootprintTable({
  analysisId,
  rows,
}: Readonly<{ analysisId: string; rows: ProductFootprint[] }>) {
  if (!rows.length) {
    return (
      <p className="empty-note">
        No product footprints are available for the selected threshold.
      </p>
    );
  }
  return (
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
                  {row.product.distribution.physical_store_distribution_count.toLocaleString()}
                </strong>
                <span>
                  positive-price stores
                  {row.product.distribution.searched_store_count
                    ? ` / ${row.product.distribution.searched_store_count.toLocaleString()} searched`
                    : ""}
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
}: Readonly<{ analysisId: string; footprint: ProductFootprint }>) {
  const mapRequestPath = useMemo(() => {
    const parameters = new URLSearchParams({
      retailer: footprint.product.retailer_id,
      product_id: footprint.product.retailer_product_id,
      detail: "summary",
    });
    return `/api/price-monitoring/${encodeURIComponent(analysisId)}/map?${parameters.toString()}`;
  }, [
    analysisId,
    footprint.product.retailer_id,
    footprint.product.retailer_product_id,
  ]);
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
            {distributionLabel(footprint.product.distribution)} ·{" "}
            {brandTypeLabels[footprint.product.brand_type]}
          </p>
        </div>
      </article>
      <ExactProductMap
        mapData={displayedMapData}
        mapError={displayedMapError}
      />
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
}: Readonly<{
  mapData: PriceMonitoringMap | null;
  mapError: string | null;
}>) {
  const visiblePoints = useMemo(
    () =>
      (mapData?.points ?? [])
        .filter(
          (point) =>
            point.status === "observed" &&
            Number.isFinite(point.latitude) &&
            Number.isFinite(point.longitude) &&
            point.latitude >= 24 &&
            point.latitude <= 50 &&
            point.longitude >= -125 &&
            point.longitude <= -66,
        )
        .slice(0, 700),
    [mapData],
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
              ? `${mapData.display.distribution_store_count.toLocaleString()} stores`
              : mapError
                ? "Unavailable"
                : "Loading…"}
          </strong>
          <p>
            {mapData
              ? `${mapData.display.search_observed_locations.toLocaleString()} positive-price Search observations; ${mapData.display.service_area_presence_count.toLocaleString()} service-area presences tracked separately.`
              : (mapError ??
                "Fetching exact product map evidence from the report API.")}
          </p>
          <div className="canonical-map-legend">
            <span className="price-lower">Below footprint median</span>
            <span className="price-parity">At median</span>
            <span className="price-higher">Above median</span>
          </div>
          {mapData?.display.observed_sampled ? (
            <small>
              Map displays a deterministic sample; the store count uses the full
              source-backed distribution set.
            </small>
          ) : null}
        </aside>
      </div>
      {mapData ? (
        <MappedLocationTable points={visiblePoints.slice(0, 12)} />
      ) : null}
    </>
  );
}

function MappedLocationTable({
  points,
}: Readonly<{ points: PriceMonitoringMapPoint[] }>) {
  if (!points.length) {
    return (
      <p className="empty-note">
        No mappable positive-price store locations were returned for this
        product.
      </p>
    );
  }
  return (
    <div className="canonical-table-wrap">
      <table className="canonical-insight-table canonical-location-table">
        <thead>
          <tr>
            <th>Mapped store sample</th>
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
  relationships,
  brandGroups,
}: Readonly<{
  relationships: ProductRelationship[];
  brandGroups: Array<{
    brandType: BrandType;
    relationships: ProductRelationship[];
  }>;
}>) {
  return (
    <>
      <section className="workspace-section">
        <header>
          <div>
            <h2>Price ladder</h2>
            <p>
              Each row is one governed product relationship with the exact
              displayed unit basis, Walmart reporting price, competitor
              reporting price, and signed gap. This is the price architecture
              view; image cards stay in the action board.
            </p>
          </div>
        </header>
        <PriceArchitectureTable relationships={relationships} />
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
              relationships={relationships.slice(0, 25)}
            />
          </section>
        ))}
    </>
  );
}

function PriceArchitectureTable({
  relationships,
}: Readonly<{ relationships: ProductRelationship[] }>) {
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
                  {relationship.benchmark_product.price.reporting_price_label}
                </strong>
                <span>{relationship.comparison.comparison_basis}</span>
              </td>
              <td>
                <strong>
                  {relationship.competitor_product.price.reporting_price_label}
                </strong>
                <span>
                  {relationship.competitor_product.retailer_product_id}
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
  title,
  note,
  relationships,
}: Readonly<{
  title: string;
  note: string;
  relationships: ProductRelationship[];
}>) {
  return (
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
              relationship={relationship}
            />
          ))}
        </div>
      ) : (
        <p className="empty-note">No included relationships in this section.</p>
      )}
    </section>
  );
}

function RelationshipCard({
  relationship,
}: Readonly<{ relationship: ProductRelationship }>) {
  const benchmarkHref = productHref(relationship.benchmark_product.url);
  const competitorHref = productHref(relationship.competitor_product.url);
  const delta = relationship.comparison.price_delta;
  const deltaLabel =
    delta >= 0
      ? `${formatCurrency(delta)} above competitor`
      : `${formatCurrency(Math.abs(delta))} below competitor`;
  const deltaExplanation = `Walmart reporting price is ${deltaLabel} on the displayed basis.`;
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
          price={relationship.benchmark_product.price.reporting_price_label}
          distribution={distributionLabel(
            relationship.benchmark_product.distribution,
          )}
        />
        <span className="canonical-versus">vs</span>
        <ProductTile
          href={competitorHref}
          title={relationship.competitor_product.title}
          imageUrl={relationship.competitor_product.image_url}
          retailer={displayLabel(relationship.competitor_product.retailer_id)}
          price={relationship.competitor_product.price.reporting_price_label}
          distribution={distributionLabel(
            relationship.competitor_product.distribution,
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
  price: string;
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
        <em>{price}</em>
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
