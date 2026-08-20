"use client";

import { useMemo, useState } from "react";

import type { CompetitivePortfolioScorecards } from "@/lib/api";
import {
  type ComparableCohort,
  type CohortOutcome,
  type CohortSort,
  sortComparableCohorts,
} from "@/lib/cohort-model";

type OutcomeFilter = "all" | Exclude<CohortOutcome, "unavailable">;

function formatCurrency(value: number | null) {
  return value === null
    ? "—"
    : value.toLocaleString("en-US", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
}

function formatRate(value: number) {
  return value.toLocaleString("en-US", {
    style: "percent",
    maximumFractionDigits: 1,
  });
}

function outcomeCopy(
  outcome: CohortOutcome,
  benchmarkName: string,
  competitorName: string,
) {
  if (outcome === "benchmark_lower") return `${benchmarkName} lower more often`;
  if (outcome === "competitor_lower")
    return `${competitorName} lower more often`;
  if (outcome === "parity") return "Price parity is most common";
  return "No directional result";
}

function gapCopy(
  gap: number | null,
  benchmarkName: string,
  competitorName: string,
) {
  if (gap === null) return "Paired median difference unavailable";
  if (Math.abs(gap) < 0.005)
    return "The paired median price difference is $0.00";
  const amount = formatCurrency(Math.abs(gap));
  return gap < 0
    ? `${competitorName} is ${amount} lower at the paired median`
    : `${benchmarkName} is ${amount} lower at the paired median`;
}

function escapeCsv(value: unknown) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

function escapeXml(value: unknown) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function exportCohorts(
  rows: Array<Record<string, string | number | null>>,
  format: "csv" | "excel",
) {
  if (!rows.length) return;
  const columns = Object.keys(rows[0]);
  const content =
    format === "csv"
      ? [
          columns.map(escapeCsv).join(","),
          ...rows.map((row) =>
            columns.map((column) => escapeCsv(row[column])).join(","),
          ),
        ].join("\n")
      : `<?xml version="1.0"?><Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"><Worksheet ss:Name="Cohort Scorecards"><Table>${[
          columns,
          ...rows.map((row) => columns.map((column) => row[column])),
        ]
          .map(
            (row) =>
              `<Row>${row
                .map(
                  (value) =>
                    `<Cell><Data ss:Type="${typeof value === "number" ? "Number" : "String"}">${escapeXml(value)}</Data></Cell>`,
                )
                .join("")}</Row>`,
          )
          .join("")}</Table></Worksheet></Workbook>`;
  const blob = new Blob([content], {
    type:
      format === "csv"
        ? "text/csv;charset=utf-8"
        : "application/vnd.ms-excel;charset=utf-8",
  });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `competitive-cohort-scorecards.${format === "csv" ? "csv" : "xls"}`;
  link.click();
  URL.revokeObjectURL(link.href);
}

export function ComparableCohortExplorer({
  benchmarkName,
  cohortDimensions,
  minimumGeographies,
  ambiguousMatches,
  onReviewMatches,
  onOpenCohort,
  pairEvidence,
  radiusCohorts,
  radiusMiles,
  radiusError,
}: Readonly<{
  benchmarkName: string;
  cohortDimensions: string[];
  minimumGeographies: number;
  ambiguousMatches: number;
  onReviewMatches: () => void;
  onOpenCohort: (cohort: ComparableCohort) => void;
  pairEvidence: Record<
    string,
    {
      pairCount: number;
      benchmarkBrandTypes: string;
      competitorBrandTypes: string;
    }
  >;
  radiusCohorts: CompetitivePortfolioScorecards["cohorts"] | null;
  radiusMiles: 1 | 3 | 5;
  radiusError: string;
}>) {
  const [outcome, setOutcome] = useState<OutcomeFilter>("all");
  const [sort, setSort] = useState<CohortSort>("evidence");
  const [showAll, setShowAll] = useState(false);
  const cohorts = useMemo(
    () =>
      (radiusCohorts ?? []).map((row): ComparableCohort => ({
        id: row.id,
        competitorId: row.competitor_id,
        competitor: row.competitor,
        profileId: row.profile_id,
        segmentId: row.segment_id,
        segment: row.segment,
        attributes: row.attributes,
        overall: false,
        matches: row.scored_product_locations,
        matchedGeographies: row.benchmark_product_locations,
        benchmarkLowerRate: row.benchmark_lower_rate ?? 0,
        competitorLowerRate: row.competitor_lower_rate ?? 0,
        parityRate: row.parity_rate ?? 0,
        benchmarkMedian: row.benchmark_median,
        competitorMedian: row.competitor_median,
        medianGap: row.paired_median_gap,
        outcome: row.dominant_outcome,
      })),
    [radiusCohorts],
  );
  const filtered = useMemo(
    () =>
      sortComparableCohorts(
        cohorts.filter(
          (cohort) => outcome === "all" || cohort.outcome === outcome,
        ),
        sort,
      ),
    [cohorts, outcome, sort],
  );
  const visible = showAll ? filtered : filtered.slice(0, 12);
  const exportRows = filtered.map((cohort) => {
    const evidence = pairEvidence[cohort.id];
    return {
      Competitor: cohort.competitor,
      Cohort: cohort.segment,
      "Governed product pairs": evidence?.pairCount ?? 0,
      [`${benchmarkName} brand-type mix`]:
        evidence?.benchmarkBrandTypes ?? "unresolved",
      "Competitor brand-type mix":
        evidence?.competitorBrandTypes ?? "unresolved",
      "Paired observations": cohort.matches,
      "Observed benchmark product-locations": cohort.matchedGeographies,
      [`Scored product-locations within ${radiusMiles} miles`]: cohort.matches,
      [`${benchmarkName} lower rate`]: cohort.benchmarkLowerRate,
      "Competitor lower rate": cohort.competitorLowerRate,
      "Parity rate": cohort.parityRate,
      [`${benchmarkName} median`]: cohort.benchmarkMedian,
      "Competitor median": cohort.competitorMedian,
      "Paired median difference": cohort.medianGap,
    };
  });
  const dimensions = cohortDimensions.length
    ? cohortDimensions.join(" · ")
    : "Product Pack matching attributes";

  if (radiusCohorts === null) {
    return (
      <section className="cohort-explorer">
        <div
          className={`empty-inline${radiusError ? " error" : ""}`}
          role="status"
        >
          {radiusError || "Loading radius-native cohort scorecards…"}
        </div>
      </section>
    );
  }

  if (!cohorts.length)
    return (
      <section className="cohort-explorer">
        <div className="empty-inline">
          No certified cohort has local comparison evidence under the selected
          retailer, basis, geography, and radius.
        </div>
      </section>
    );

  return (
    <section className="cohort-explorer">
      <header className="cohort-explorer-header">
        <div>
          <p className="eyebrow">Comparable cohort explorer</p>
          <h2>Category rollups without weakening item-level match integrity</h2>
          <p>
            Each row summarizes certified one-to-one product relationships at
            observed benchmark product-store grain. Physical competitor evidence
            must fall within {radiusMiles} mile{radiusMiles === 1 ? "" : "s"};
            service-area retailers use the same delivery ZIP.
          </p>
        </div>
        <button type="button" onClick={onReviewMatches}>
          Review item relationships
          {ambiguousMatches ? ` · ${ambiguousMatches} ambiguous` : ""}
        </button>
      </header>

      <p className="cohort-dimension-note">
        Governed cohort attributes: {dimensions}. Open any row to inspect its
        included one-to-one product relationships.
      </p>

      <div className="cohort-toolbar">
        <div role="group" aria-label="Cohort outcome">
          {(
            [
              ["all", `All cohorts (${cohorts.length})`],
              ["benchmark_lower", `${benchmarkName} lower`],
              ["competitor_lower", "Competitor lower"],
              ["parity", "Parity"],
            ] as const
          ).map(([value, label]) => (
            <button
              type="button"
              className={outcome === value ? "active" : ""}
              aria-pressed={outcome === value}
              onClick={() => {
                setOutcome(value);
                setShowAll(false);
              }}
              key={value}
            >
              {label}
            </button>
          ))}
        </div>
        <label>
          <span>Rank cohorts by</span>
          <select
            value={sort}
            onChange={(event) => setSort(event.target.value as CohortSort)}
          >
            <option value="evidence">Broadest matched evidence</option>
            <option value="competitor_pressure">
              Competitor lower-price share
            </option>
            <option value="gap">Largest paired median difference</option>
          </select>
        </label>
        <div className="cohort-export-actions">
          <button
            type="button"
            onClick={() => exportCohorts(exportRows, "csv")}
          >
            Download CSV
          </button>
          <button
            type="button"
            onClick={() => exportCohorts(exportRows, "excel")}
          >
            Download Excel
          </button>
        </div>
      </div>

      <div className="cohort-list">
        {visible.map((cohort) => {
          const limited = cohort.matches < minimumGeographies;
          const evidence = pairEvidence[cohort.id];
          return (
            <button
              type="button"
              className={`cohort-row ${cohort.outcome}`}
              key={cohort.id}
              onClick={() => onOpenCohort(cohort)}
              aria-label={`View products included in ${cohort.segment} for ${cohort.competitor}`}
            >
              <div className="cohort-title">
                <span>{cohort.competitor}</span>
                <h3>{cohort.segment}</h3>
                <p>
                  {cohort.matches.toLocaleString()} scored product-locations ·{" "}
                  {cohort.matchedGeographies.toLocaleString()} observed
                  benchmark product-locations
                </p>
                <div className="cohort-pair-evidence">
                  <strong>
                    {(evidence?.pairCount ?? 0).toLocaleString()} governed
                    product pairs
                  </strong>
                  <span>
                    {benchmarkName}:{" "}
                    {evidence?.benchmarkBrandTypes ?? "brand type unresolved"}
                  </span>
                  <span>
                    {cohort.competitor}:{" "}
                    {evidence?.competitorBrandTypes ?? "brand type unresolved"}
                  </span>
                </div>
              </div>
              <div className="cohort-outcome">
                <span>
                  {outcomeCopy(
                    cohort.outcome,
                    benchmarkName,
                    cohort.competitor,
                  )}
                </span>
                <strong>
                  {gapCopy(cohort.medianGap, benchmarkName, cohort.competitor)}
                </strong>
                <small className={limited ? "limited" : "ready"}>
                  {limited
                    ? `Directional · below ${minimumGeographies} observation threshold`
                    : "Decision-grade local evidence"}
                </small>
              </div>
              <div className="cohort-share" aria-label="Lower-price share">
                <div>
                  <span>
                    {benchmarkName}
                    <b>{formatRate(cohort.benchmarkLowerRate)}</b>
                  </span>
                  <i>
                    <b
                      className="benchmark"
                      style={{
                        width: `${Math.max(1, cohort.benchmarkLowerRate * 100)}%`,
                      }}
                    />
                  </i>
                </div>
                <div>
                  <span>
                    {cohort.competitor}
                    <b>{formatRate(cohort.competitorLowerRate)}</b>
                  </span>
                  <i>
                    <b
                      className="competitor"
                      style={{
                        width: `${Math.max(1, cohort.competitorLowerRate * 100)}%`,
                      }}
                    />
                  </i>
                </div>
                <small>{formatRate(cohort.parityRate)} parity</small>
              </div>
              <dl className="cohort-medians">
                <div>
                  <dt>{benchmarkName} median</dt>
                  <dd>{formatCurrency(cohort.benchmarkMedian)}</dd>
                </div>
                <div>
                  <dt>{cohort.competitor} median</dt>
                  <dd>{formatCurrency(cohort.competitorMedian)}</dd>
                </div>
              </dl>
              <span className="cohort-row-action">
                View included products →
              </span>
            </button>
          );
        })}
        {!visible.length ? (
          <div className="cohort-empty">
            <strong>No cohorts have this outcome.</strong>
            <p>
              Choose another outcome filter while keeping the current competitor
              and lens.
            </p>
          </div>
        ) : null}
      </div>
      {filtered.length > 12 ? (
        <button
          className="cohort-show-more"
          type="button"
          onClick={() => setShowAll(!showAll)}
        >
          {showAll
            ? "Show highest-signal cohorts"
            : `Show all ${filtered.length} cohorts`}
        </button>
      ) : null}
      <footer>
        Search supplies store-specific price and location. The API projects
        certified relationships into product-location outcomes before this page
        receives rates or medians; the browser does not recalculate them.
      </footer>
    </section>
  );
}
