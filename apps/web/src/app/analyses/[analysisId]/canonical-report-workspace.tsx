"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { RetailCompetitiveIntelligenceCanonicalReportDataset } from "@rci/contracts";

import type { AnalysisRecord, AnalysisReportView } from "@/lib/api";
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
type BrandType = ProductRelationship["benchmark_product"]["brand_type"];

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
          <p className="eyebrow">Simplified report preview</p>
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
            <span>Preview only</span>
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
            Current report
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
            relationships={broadWalmartRelationships}
            totalRelationships={dataset.product_relationships.length}
          />
        ) : null}
        {activeTab === "Price Architecture" ? (
          <PriceArchitecture brandGroups={brandGroups} />
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
  const topLosses = groups.walmartLosses.slice(0, 6);
  const topWins = groups.walmartWins.slice(0, 6);
  return (
    <>
      <section className="workspace-section">
        <header>
          <div>
            <h2>What matters now</h2>
            <p>
              This preview prioritizes product-level decisions over rollups. A
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
      {topLosses.length ? (
        <RelationshipSection
          title="Top Walmart losses by product footprint"
          note="Every card is image-first and uses the governed reporting price."
          relationships={topLosses}
        />
      ) : null}
      {topWins.length ? (
        <RelationshipSection
          title="Top Walmart wins by product footprint"
          note="Sorted by positive-price Walmart store distribution."
          relationships={topWins}
        />
      ) : null}
    </>
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
  relationships,
  totalRelationships,
}: Readonly<{
  relationships: ProductRelationship[];
  totalRelationships: number;
}>) {
  return (
    <>
      <section className="workspace-section">
        <header>
          <div>
            <h2>Broad Walmart distribution</h2>
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
            <strong>{relationships.length.toLocaleString()}</strong>
            <p>
              Included relationships with at least 1,000 positive-price Walmart
              stores out of {totalRelationships.toLocaleString()} total included
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
        </div>
      </section>
      <RelationshipSection
        title="Product footprint cards"
        note="Image cards make every relationship reviewable without burying key products in table rows."
        relationships={relationships}
      />
    </>
  );
}

function PriceArchitecture({
  brandGroups,
}: Readonly<{
  brandGroups: Array<{
    brandType: BrandType;
    relationships: ProductRelationship[];
  }>;
}>) {
  return (
    <>
      {brandGroups
        .filter(({ relationships }) => relationships.length > 0)
        .map(({ brandType, relationships }) => (
          <RelationshipSection
            key={brandType}
            title={`${brandTypeLabels[brandType]} (${relationships.length.toLocaleString()})`}
            note={
              brandType === "regional"
                ? "Fact-only section: included regional relationships with governed prices and distribution."
                : "Included relationships grouped by Walmart brand classification."
            }
            relationships={relationships}
          />
        ))}
    </>
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
