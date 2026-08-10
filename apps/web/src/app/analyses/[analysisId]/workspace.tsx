"use client";

import { useState } from "react";

import { DataTable } from "@/app/components/data-table";
import type {
  AnalysisRecord,
  AnalysisReportView,
  JsonObject,
  MapPoint,
  ProductHighlight,
  ReportSectionView,
} from "@/lib/api";
import {
  asObject,
  asRows,
  displayDate,
  displayLabel,
  displayValue,
} from "@/lib/presentation";
import {
  compactMetricName,
  formatMetric,
  groupReportSections,
  metricBarWidth,
  primaryComparisonRows,
} from "@/lib/report-presentation";

const tabs = [
  "Executive Summary",
  "Geographic Coverage",
  "Price Position",
  "Segment Analysis",
  "Product Matches",
  "Assortment",
  "Data Quality / QA",
  "Methodology",
  "Exports",
] as const;

type Tab = (typeof tabs)[number];

export function AnalysisWorkspace({
  analysis,
  reportView,
}: Readonly<{
  analysis: AnalysisRecord;
  reportView: AnalysisReportView | null;
}>) {
  return reportView ? (
    <BlueprintAnalysisWorkspace analysis={analysis} reportView={reportView} />
  ) : (
    <LegacyAnalysisWorkspace analysis={analysis} />
  );
}

function LegacyAnalysisWorkspace({
  analysis,
}: Readonly<{ analysis: AnalysisRecord }>) {
  const [activeTab, setActiveTab] = useState<Tab>(tabs[0]);
  const result = analysis.result as unknown as JsonObject;
  const productPack = asObject(result.product_pack);
  const validation = asObject(result.validation);
  return (
    <>
      <header className="workspace-header">
        <div>
          <p className="eyebrow">Analysis workspace</p>
          <h1>
            {displayLabel(String(productPack.id ?? analysis.product_pack_id))}
          </h1>
          <p className="workspace-meta">
            {analysis.analysis_id} · Generated{" "}
            {displayDate(String(result.generated_at))}
          </p>
        </div>
        <div className="workspace-status">
          <span className={`status-badge ${analysis.status}`}>
            {displayLabel(analysis.status)}
          </span>
          <small>Schema {analysis.schema_version}</small>
        </div>
      </header>
      <div className="tab-list" role="tablist" aria-label="Analysis sections">
        {tabs.map((tab) => (
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
        {activeTab === "Executive Summary" && (
          <ExecutiveSummary result={result} validation={validation} />
        )}
        {activeTab === "Geographic Coverage" && (
          <Section
            title="Geographic coverage"
            note="Fresh ZIP and store coverage supplied by the canonical result."
          >
            <DataTable rows={asRows(result.coverage)} />
          </Section>
        )}
        {activeTab === "Price Position" && (
          <Section
            title="Price position"
            note="Persisted competitive metrics by retailer and segment."
          >
            <DataTable rows={asRows(result.comparisons)} />
          </Section>
        )}
        {activeTab === "Segment Analysis" && (
          <>
            <Section
              title="Configured segments"
              note="Product Pack attributes that define comparable groups."
            >
              <DataTable rows={asRows(result.segments)} />
            </Section>
            <Section title="Segment outcomes">
              <DataTable rows={asRows(result.comparisons)} />
            </Section>
          </>
        )}
        {activeTab === "Product Matches" && (
          <MatchDrilldown
            comparisons={asRows(result.comparisons)}
            provenance={asObject(result.provenance)}
          />
        )}
        {activeTab === "Assortment" && (
          <>
            <Section
              title="Source assortment"
              note="Collection inputs and available canonical segment detail."
            >
              <ObjectGrid value={asObject(result.source_summary)} />
            </Section>
            <Section title="Classified segments">
              <DataTable rows={asRows(result.segments)} />
            </Section>
          </>
        )}
        {activeTab === "Data Quality / QA" && (
          <>
            <Section
              title="Data quality"
              note="Authoritative flags emitted by the analytics pipeline."
            >
              <ObjectGrid value={asObject(result.data_quality)} />
            </Section>
            <Section title="Validation evidence">
              <ObjectGrid value={validation} />
              <DataTable rows={asRows(validation.checks)} />
            </Section>
          </>
        )}
        {activeTab === "Methodology" && (
          <>
            <Section title="Product Pack">
              <ObjectGrid value={productPack} />
            </Section>
            <Section
              title="Provenance"
              note="Source and benchmark lineage persisted with this result."
            >
              <ObjectGrid value={asObject(result.provenance)} />
            </Section>
          </>
        )}
        {activeTab === "Exports" && (
          <Section
            title="Delivery artifacts"
            note="Generated from this immutable AnalysisResult; renderers do not recalculate metrics."
          >
            <ArtifactActions analysisId={analysis.analysis_id} />
          </Section>
        )}
      </section>
    </>
  );
}

function BlueprintAnalysisWorkspace({
  analysis,
  reportView,
}: Readonly<{
  analysis: AnalysisRecord;
  reportView: AnalysisReportView;
}>) {
  const groupedSections = groupReportSections(reportView.sections);
  const firstPopulatedGroup =
    groupedSections.find((group) => group.sections.length > 0)?.id ?? "summary";
  const [activeGroup, setActiveGroup] = useState<string>(firstPopulatedGroup);
  const selectedGroup = groupedSections.find(
    (group) => group.id === activeGroup,
  );
  const publication = reportView.publication;
  const recommendedCharts = reportView.product_pack.recommended_charts ?? [];
  const primaryComparisons = primaryComparisonRows(reportView.sections);
  return (
    <>
      <header className="workspace-header report-header">
        <div>
          <p className="eyebrow">Competitive intelligence report</p>
          <h1>{reportView.product_pack.name}</h1>
          <p className="report-deck">
            Where the price war is being won, where it is being lost, and which
            targeted moves matter most.
          </p>
          <p className="workspace-meta">
            {analysis.analysis_id} · Generated{" "}
            {displayDate(reportView.generated_at)}
          </p>
          <div className="trust-strip" aria-label="Result integrity">
            <span>Deterministic metrics</span>
            <span>Evidence linked</span>
            {publication ? <span>Published v{publication.version}</span> : null}
            <span title={reportView.result_checksum}>
              Checksum {reportView.result_checksum.slice(0, 12)}…
            </span>
          </div>
        </div>
        <div className="workspace-status">
          <span
            className={`status-badge ${publication?.status ?? analysis.status}`}
          >
            {displayLabel(publication?.status ?? analysis.status)}
          </span>
          <ArtifactDownloadButton
            analysisId={analysis.analysis_id}
            artifactType="html"
            label="Open shareable report"
            className="button primary report-action"
          />
          <small>
            Blueprint {reportView.blueprint.id} · {reportView.blueprint.version}
          </small>
        </div>
      </header>
      <div className="tab-list" role="tablist" aria-label="Analysis sections">
        {groupedSections.map((group) => (
          <button
            type="button"
            role="tab"
            aria-selected={activeGroup === group.id}
            className={activeGroup === group.id ? "active" : ""}
            onClick={() => setActiveGroup(group.id)}
            key={group.id}
          >
            {group.label}
          </button>
        ))}
        <button
          type="button"
          role="tab"
          aria-selected={activeGroup === "exports"}
          className={activeGroup === "exports" ? "active" : ""}
          onClick={() => setActiveGroup("exports")}
        >
          Exports
        </button>
      </div>
      <section className="workspace-panel" role="tabpanel">
        {activeGroup === "exports" ? (
          <Section
            title="Delivery artifacts"
            note="Every format presents the same immutable AnalysisResult and carries its shared result checksum."
          >
            <ArtifactActions analysisId={analysis.analysis_id} />
          </Section>
        ) : selectedGroup && selectedGroup.sections.length > 0 ? (
          <>
            {activeGroup === "summary" && primaryComparisons.length > 0 ? (
              <DecisionScorecard rows={primaryComparisons} />
            ) : null}
            {activeGroup === "geography" && reportView.map_points?.length ? (
              <AnalysisMap points={reportView.map_points} />
            ) : null}
            {activeGroup === "geography" ? (
              <ComparableMarketCoverage rows={primaryComparisons} />
            ) : null}
            {activeGroup === "products" &&
            reportView.product_highlights?.length ? (
              <ProductHighlights products={reportView.product_highlights} />
            ) : null}
            {selectedGroup.sections
              .filter((section) => section.kind !== "kpi_strip")
              .map((section) => (
                <BlueprintSection
                  section={section}
                  recommendedCharts={recommendedCharts}
                  benchmarkRetailer={reportView.benchmark_retailer}
                  key={section.id}
                />
              ))}
          </>
        ) : (
          <Section
            title={selectedGroup?.label ?? "Analysis section"}
            note="This Product Pack does not define content for this workspace section."
          >
            <p className="empty-copy">
              No decision-ready records were supplied for this section.
            </p>
          </Section>
        )}
      </section>
    </>
  );
}

function BlueprintSection({
  section,
  recommendedCharts,
  benchmarkRetailer,
}: Readonly<{
  section: ReportSectionView;
  recommendedCharts: string[];
  benchmarkRetailer: string;
}>) {
  const narrative = asObject(section.narrative);
  const visibleMetrics =
    section.kind === "coverage" ? [] : section.metrics.slice(0, 6);
  const metricValues = visibleMetrics.map((metric) => metric.value);
  const comparisonChart = shouldShowComparisonChart(section, recommendedCharts);
  const narrativeLeads =
    Boolean(narrative.body) &&
    ["executive_summary", "recommendations"].includes(section.kind);
  return (
    <Section
      title={section.title}
      note={`${displayLabel(section.kind)} · ${displayLabel(section.visualization)}`}
    >
      {narrative.body ? (
        <div className="section-narrative">
          {displayValue(narrative.body)
            .split(/\n{2,}/)
            .map((paragraph) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
        </div>
      ) : null}
      {visibleMetrics.length > 0 && section.visualization === "bar" ? (
        <div className="metric-bars" aria-label={`${section.title} metrics`}>
          {visibleMetrics.map((metric) => (
            <div className="metric-bar" key={String(metric.metric_id)}>
              <div>
                <span>{compactMetricName(metric, benchmarkRetailer)}</span>
                <strong>{formatMetric(metric.value, metric.unit)}</strong>
              </div>
              <i aria-hidden="true">
                <b
                  style={{
                    width: `${metricBarWidth(metric.value, metricValues)}%`,
                  }}
                />
              </i>
            </div>
          ))}
        </div>
      ) : visibleMetrics.length > 0 ? (
        <div className="metric-grid">
          {visibleMetrics.map((metric) => (
            <Metric
              key={String(metric.metric_id)}
              label={compactMetricName(metric, benchmarkRetailer)}
              value={formatMetric(metric.value, metric.unit)}
            />
          ))}
        </div>
      ) : null}
      {comparisonChart ? (
        <CompetitivePositionChart
          rows={section.records}
          title={section.title}
        />
      ) : null}
      {section.records.length > 0 &&
      section.visualization === "ranked_cards" &&
      !narrativeLeads ? (
        <DecisionCards rows={section.records} />
      ) : section.records.length > 0 &&
        section.kind !== "kpi_strip" &&
        section.kind !== "coverage" &&
        !narrativeLeads &&
        !comparisonChart ? (
        <DataTable rows={section.records} />
      ) : null}
      {comparisonChart || (narrativeLeads && section.records.length > 0) ? (
        <details className="evidence-disclosure report-detail">
          <summary>View supporting detail</summary>
          <DataTable rows={section.records} />
        </details>
      ) : null}
      {section.evidence_sets.length > 0 ? (
        <details className="evidence-disclosure">
          <summary>Evidence manifests</summary>
          <DataTable rows={section.evidence_sets} />
        </details>
      ) : null}
      {section.empty ? (
        <p className="empty-copy">
          {section.empty_state ?? "No records were supplied for this section."}
        </p>
      ) : null}
    </Section>
  );
}

function DecisionScorecard({ rows }: Readonly<{ rows: JsonObject[] }>) {
  return (
    <Section
      title="Competitive scorecard"
      note="Strict comparable-package outcomes by competitor; matched observations and signed price gaps remain visible for context."
    >
      <CompetitivePositionChart rows={rows} title="Competitive scorecard" />
    </Section>
  );
}

function ComparableMarketCoverage({ rows }: Readonly<{ rows: JsonObject[] }>) {
  const coverage = rows
    .map((row) => ({
      competitor: displayValue(row.competitor),
      geographies: parseCount(row["matched geographies"]),
      matches: parseCount(row.matches),
    }))
    .filter((row) => row.geographies > 0)
    .sort((left, right) => right.geographies - left.geographies);
  const maximum = Math.max(...coverage.map((row) => row.geographies), 0);
  if (coverage.length === 0) return null;
  return (
    <Section
      title="Comparable market coverage"
      note="Distinct geographies with strict package comparisons—not raw retailer footprint or source-row volume."
    >
      <figure className="market-coverage-chart">
        {coverage.map((row) => (
          <div key={row.competitor}>
            <span>
              <strong>{row.competitor}</strong>
              <small>{row.matches.toLocaleString()} matched observations</small>
            </span>
            <i aria-hidden="true">
              <b style={{ width: `${(row.geographies / maximum) * 100}%` }} />
            </i>
            <em>{row.geographies.toLocaleString()} geographies</em>
          </div>
        ))}
      </figure>
    </Section>
  );
}

const chartCapabilityBySection: Record<string, string[]> = {
  price_position: ["package_price_gap", "exact_match", "price_position"],
  segment_analysis: ["price_per_lb", "normalized_price", "segment_win_rate"],
  geographic_sensitivity: ["radius_sensitivity", "proximity"],
};

function shouldShowComparisonChart(
  section: ReportSectionView,
  recommendedCharts: string[],
) {
  const capabilities = chartCapabilityBySection[section.kind];
  if (!capabilities || section.records.length === 0) return false;
  return capabilities.some((capability) =>
    recommendedCharts.includes(capability),
  );
}

function parseRate(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value <= 1 ? value * 100 : value;
  }
  if (typeof value !== "string") return null;
  const parsed = Number.parseFloat(value.replace(/[%,$]/g, ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function parseCount(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string") return 0;
  const parsed = Number.parseFloat(value.replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

function CompetitivePositionChart({
  rows,
  title,
}: Readonly<{ rows: JsonObject[]; title: string }>) {
  const chartRows = rows
    .map((row) => ({
      row,
      competitorRate: parseRate(row["competitor lower"]),
      benchmarkRate: parseRate(row["benchmark lower"]),
      matches: parseCount(row.matches),
      geographies: parseCount(row["matched geographies"]),
    }))
    .filter(
      (item) => item.competitorRate !== null || item.benchmarkRate !== null,
    )
    .sort((left, right) => right.matches - left.matches)
    .slice(0, 8);
  if (chartRows.length === 0) return null;
  return (
    <figure className="comparison-chart" aria-label={`${title} comparison`}>
      <figcaption>
        <div>
          <strong>Lower-price share</strong>
          <span>
            Strict comparable-package outcomes with market coverage and signed
            gap
          </span>
        </div>
        <div className="chart-legend" aria-label="Chart legend">
          <span className="benchmark">Benchmark</span>
          <span className="competitor">Competitor</span>
        </div>
      </figcaption>
      <div className="comparison-chart-body">
        {chartRows.map(
          (
            { row, benchmarkRate, competitorRate, matches, geographies },
            index,
          ) => (
            <div className="comparison-chart-row" key={String(row.id ?? index)}>
              <div className="comparison-chart-label">
                <strong>{displayValue(row.segment ?? row.competitor)}</strong>
                <span>
                  {displayValue(row.competitor)} · {matches.toLocaleString()}{" "}
                  matches
                  {geographies > 0
                    ? ` · ${geographies.toLocaleString()} geographies`
                    : ""}
                  {row["competitor - benchmark gap"]
                    ? ` · gap ${displayValue(row["competitor - benchmark gap"])}`
                    : ""}
                </span>
              </div>
              <div className="paired-bars">
                <div>
                  <i>
                    <b
                      className="benchmark"
                      style={{ width: `${Math.max(benchmarkRate ?? 0, 1)}%` }}
                    />
                  </i>
                  <span>
                    {benchmarkRate === null
                      ? "—"
                      : `${benchmarkRate.toFixed(1)}%`}
                  </span>
                </div>
                <div>
                  <i>
                    <b
                      className="competitor"
                      style={{ width: `${Math.max(competitorRate ?? 0, 1)}%` }}
                    />
                  </i>
                  <span>
                    {competitorRate === null
                      ? "—"
                      : `${competitorRate.toFixed(1)}%`}
                  </span>
                </div>
              </div>
            </div>
          ),
        )}
      </div>
      <p className="chart-note">
        Directional share among matched observations; open the supporting detail
        for exact definitions and caveats.
      </p>
    </figure>
  );
}

function ProductHighlights({
  products,
}: Readonly<{ products: ProductHighlight[] }>) {
  return (
    <Section
      title="Products to know"
      note="PDP-enriched identity and imagery; search observations remain authoritative for price."
    >
      <div className="product-highlight-grid">
        {products.slice(0, 8).map((product) => {
          const content = (
            <>
              <div className="product-image" aria-hidden="true">
                {product.image_url ? (
                  // External retailer images are presentation-only and intentionally unoptimized.
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={product.image_url} alt="" loading="lazy" />
                ) : (
                  <span>{product.name.slice(0, 1)}</span>
                )}
              </div>
              <div>
                <span className="product-retailer">{product.retailer}</span>
                <h3>{product.name}</h3>
                {product.brand ? <p>{product.brand}</p> : null}
                {product.role ? <b>{product.role}</b> : null}
              </div>
            </>
          );
          return product.url ? (
            <a
              className="product-highlight"
              href={product.url}
              target="_blank"
              rel="noreferrer"
              key={product.canonical_product_id}
            >
              {content}
            </a>
          ) : (
            <article
              className="product-highlight"
              key={product.canonical_product_id}
            >
              {content}
            </article>
          );
        })}
      </div>
    </Section>
  );
}

function AnalysisMap({ points }: Readonly<{ points: MapPoint[] }>) {
  const products = Array.from(
    new Map(
      points
        .filter((point) => point.benchmark_product_id)
        .map((point) => [
          String(point.benchmark_product_id),
          point.benchmark_product_name ?? point.label,
        ]),
    ),
  ).sort((left, right) => left[1].localeCompare(right[1]));
  const [selectedProduct, setSelectedProduct] = useState("all");
  const positioned = points
    .filter(
      (point) =>
        Number.isFinite(point.latitude) &&
        Number.isFinite(point.longitude) &&
        point.latitude >= 24 &&
        point.latitude <= 50 &&
        point.longitude >= -125 &&
        point.longitude <= -66 &&
        (selectedProduct === "all" ||
          point.benchmark_product_id === selectedProduct),
    )
    .slice(0, 3000);
  const outcomeCounts = positioned.reduce(
    (counts, point) => {
      const outcome = point.outcome ?? "parity";
      counts[outcome] = (counts[outcome] ?? 0) + (point.matches ?? 1);
      return counts;
    },
    {} as Record<string, number>,
  );
  const projectedOutline = [
    [-124.7, 48.4],
    [-123, 46],
    [-124, 42],
    [-122, 38],
    [-117, 32.5],
    [-111, 31.4],
    [-106.5, 31.8],
    [-103, 29.7],
    [-97, 25.8],
    [-90, 29],
    [-83, 25.5],
    [-80, 27],
    [-80, 32],
    [-75, 35],
    [-75, 39],
    [-67, 45],
    [-71, 47],
    [-83, 47],
    [-95, 49],
    [-105, 49],
    [-116, 49],
    [-124.7, 48.4],
  ]
    .map(([longitude, latitude], index) => {
      const x = ((longitude + 125) / 59) * 900 + 30;
      const y = ((50 - latitude) / 26) * 460 + 30;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <Section
      title="Benchmark-product price map"
      note={`${positioned.length.toLocaleString()} evidence-linked comparison locations in the continental U.S.`}
    >
      <div className="map-controls">
        <label>
          <span>Benchmark product</span>
          <select
            value={selectedProduct}
            onChange={(event) => setSelectedProduct(event.target.value)}
          >
            <option value="all">All mapped benchmark products</option>
            {products.map(([id, name]) => (
              <option value={id} key={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <div className="map-legend" aria-label="Map outcome legend">
          <span className="benchmark_lower">
            Benchmark lower ·{" "}
            {(outcomeCounts.benchmark_lower ?? 0).toLocaleString()}
          </span>
          <span className="competitor_lower">
            Competitor lower ·{" "}
            {(outcomeCounts.competitor_lower ?? 0).toLocaleString()}
          </span>
          <span className="parity">
            Parity · {(outcomeCounts.parity ?? 0).toLocaleString()}
          </span>
        </div>
      </div>
      <figure className="analysis-map">
        <svg
          viewBox="0 0 960 520"
          role="img"
          aria-label="Analysis-linked geographic locations"
        >
          <rect width="960" height="520" rx="22" />
          <path className="us-outline" d={`${projectedOutline} Z`} />
          {positioned.map((point) => {
            const x = ((point.longitude + 125) / 59) * 900 + 30;
            const y = ((50 - point.latitude) / 26) * 460 + 30;
            return (
              <circle
                cx={x}
                cy={y}
                r="4.5"
                className={point.outcome ?? "parity"}
                key={point.id}
              >
                <title>
                  {point.benchmark_product_name ?? point.label}
                  {point.zipcode ? ` · ZIP ${point.zipcode}` : ""}
                  {point.competitor
                    ? ` · vs. ${displayLabel(point.competitor)}`
                    : ""}
                  {point.value_label ? ` · ${point.value_label}` : ""}
                </title>
              </circle>
            );
          })}
        </svg>
        <figcaption>
          Filter by benchmark product, then hover a point for its ZIP,
          competitor, and signed price-gap evidence. PDP data does not drive
          these price outcomes.
        </figcaption>
      </figure>
    </Section>
  );
}

function DecisionCards({ rows }: Readonly<{ rows: JsonObject[] }>) {
  return (
    <div className="decision-card-grid">
      {rows.map((row, index) => {
        const rank = row.priority ?? row.severity ?? index + 1;
        const headline =
          row.summary ??
          row.action ??
          row.title ??
          row.text ??
          "Decision signal";
        const detail = row.detail ?? row.rationale ?? row.description;
        return (
          <article className="decision-card" key={String(row.id ?? index)}>
            <span>{displayValue(rank)}</span>
            <h3>{displayValue(headline)}</h3>
            {detail ? <p>{displayValue(detail)}</p> : null}
          </article>
        );
      })}
    </div>
  );
}

function ExecutiveSummary({
  result,
  validation,
}: Readonly<{ result: JsonObject; validation: JsonObject }>) {
  const findings = asRows(result.findings);
  const recommendations = asRows(result.recommendations);
  const source = asObject(result.source_summary);
  return (
    <>
      <div className="metric-grid">
        <Metric label="Validation" value={validation.status} />
        <Metric label="Benchmark" value={result.benchmark_retailer} />
        <Metric label="Source rows" value={source.total_rows} />
        <Metric
          label="Competitors"
          value={
            Array.isArray(result.competitors) ? result.competitors.length : 0
          }
        />
      </div>
      <Section title="What matters">
        <div className="finding-grid">
          {findings.map((finding, index) => (
            <article className="finding" key={String(finding.id ?? index)}>
              <span>{displayValue(finding.severity)}</span>
              <p>{displayValue(finding.text)}</p>
            </article>
          ))}
        </div>
      </Section>
      <Section title="Recommended actions">
        <ol className="recommendations">
          {recommendations.map((recommendation, index) => (
            <li key={index}>
              <b>{displayValue(recommendation.priority)}</b>
              <span>{displayValue(recommendation.text)}</span>
            </li>
          ))}
        </ol>
      </Section>
    </>
  );
}

function MatchDrilldown({
  comparisons,
  provenance,
}: Readonly<{ comparisons: JsonObject[]; provenance: JsonObject }>) {
  return (
    <Section
      title="Match drilldown"
      note="One row per persisted competitor/segment comparison, with lineage alongside it."
    >
      <div className="match-grid">
        {comparisons.map((comparison, index) => (
          <article className="match-card" key={index}>
            <header>
              <span>
                {displayLabel(String(comparison.competitor_id ?? "competitor"))}
              </span>
              <b>{displayLabel(String(comparison.segment_id ?? "segment"))}</b>
            </header>
            <ObjectGrid value={comparison} />
          </article>
        ))}
      </div>
      <div className="provenance-strip">
        <b>Evidence provenance</b>
        <span>{displayValue(provenance)}</span>
      </div>
    </Section>
  );
}

function Section({
  title,
  note,
  children,
}: Readonly<{ title: string; note?: string; children: React.ReactNode }>) {
  return (
    <section className="workspace-section">
      <header>
        <div>
          <h2>{title}</h2>
          {note && <p>{note}</p>}
        </div>
      </header>
      {children}
    </section>
  );
}

function Metric({ label, value }: Readonly<{ label: string; value: unknown }>) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{displayValue(value)}</strong>
    </div>
  );
}

function ObjectGrid({ value }: Readonly<{ value: JsonObject }>) {
  return (
    <dl className="object-grid">
      {Object.entries(value)
        .filter(([key]) => key !== "checks")
        .map(([key, item]) => (
          <div key={key}>
            <dt>{displayLabel(key)}</dt>
            <dd>{displayValue(item)}</dd>
          </div>
        ))}
    </dl>
  );
}

function ArtifactDownloadButton({
  analysisId,
  artifactType,
  label,
  className,
}: Readonly<{
  analysisId: string;
  artifactType: string;
  label: string;
  className?: string;
}>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function openArtifact() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(
        `/api/analyses/${encodeURIComponent(analysisId)}/artifacts/${artifactType}`,
        { method: "POST" },
      );
      const body = (await response.json()) as {
        download_url?: string;
        error?: string;
      };
      if (!response.ok || !body.download_url) {
        throw new Error(body.error ?? "Report generation failed.");
      }
      window.open(body.download_url, "_blank", "noopener,noreferrer");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Report generation failed.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="report-action-wrap">
      <button
        type="button"
        className={className}
        onClick={() => void openArtifact()}
        disabled={busy}
      >
        {busy ? "Preparing report…" : label}
      </button>
      {error ? (
        <small className="form-error" role="alert">
          {error}
        </small>
      ) : null}
    </div>
  );
}

function ArtifactActions({ analysisId }: Readonly<{ analysisId: string }>) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const artifacts = [
    ["html", "Report (HTML)"],
    ["xlsx", "Excel audit workbook"],
    ["leadership_email", "Email draft + attached report"],
    ["audit_zip", "Complete audit package"],
  ] as const;
  async function generate(type: string) {
    setBusy(type);
    setMessage("");
    try {
      const response = await fetch(
        `/api/analyses/${encodeURIComponent(analysisId)}/artifacts/${type}`,
        { method: "POST" },
      );
      const body = (await response.json()) as {
        download_url?: string;
        error?: string;
      };
      if (!response.ok || !body.download_url)
        throw new Error(body.error ?? "Artifact generation failed.");
      window.location.assign(body.download_url);
      setMessage("Artifact generated. Your secure download is opening now.");
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Artifact generation failed.",
      );
    } finally {
      setBusy("");
    }
  }
  return (
    <div className="export-grid">
      {artifacts.map(([type, label]) => (
        <button
          type="button"
          onClick={() => void generate(type)}
          disabled={Boolean(busy)}
          key={type}
        >
          <span>{label}</span>
          <b>{busy === type ? "Generating…" : "Generate & download"}</b>
        </button>
      ))}
      {message && (
        <p className="action-message" role="status">
          {message}
        </p>
      )}
    </div>
  );
}
