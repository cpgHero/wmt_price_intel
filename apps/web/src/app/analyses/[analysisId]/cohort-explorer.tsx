"use client";

import { useMemo, useState } from "react";

import type { CompetitivePortfolioScorecards } from "@/lib/api";
import {
  type ComparableCohort,
  type CohortOutcome,
  type CohortSort,
  cohortPackageEquivalent,
  cohortPricePresentation,
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

function formatCohortCurrency(value: number | null, unitLabel: string) {
  const normalized = unitLabel.toLowerCase();
  const unitPrice =
    normalized.includes("fl oz") && !normalized.includes("package");
  return value === null
    ? "—"
    : value.toLocaleString("en-US", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: unitPrice ? 4 : 2,
        maximumFractionDigits: unitPrice ? 4 : 2,
      });
}

function formatRate(value: number) {
  return value.toLocaleString("en-US", {
    style: "percent",
    maximumFractionDigits: 1,
  });
}

function contributingLocationLabel(
  stores: number,
  serviceAreas: number,
  fallbackLocations: number,
) {
  if (serviceAreas && !stores)
    return `${serviceAreas.toLocaleString()} delivery ZIP${serviceAreas === 1 ? "" : "s"}`;
  if (stores && !serviceAreas)
    return `${stores.toLocaleString()} competitor store${stores === 1 ? "" : "s"}`;
  return `${fallbackLocations.toLocaleString()} competitor location${fallbackLocations === 1 ? "" : "s"}`;
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
  unitLabel = "",
) {
  if (gap === null) return "Paired median difference unavailable";
  const normalizedUnit = unitLabel.toLowerCase();
  const unitPrice =
    normalizedUnit.includes("fl oz") && !normalizedUnit.includes("package");
  if (Math.abs(gap) < (unitPrice ? 0.00005 : 0.005))
    return "The paired median price difference is $0.00";
  const amount = unitLabel
    ? formatCohortCurrency(Math.abs(gap), unitLabel)
    : formatCurrency(Math.abs(gap));
  const unit = unitLabel ? ` ${unitLabel}` : "";
  return gap < 0
    ? `${competitorName} is ${amount}${unit} lower at the paired median`
    : `${benchmarkName} is ${amount}${unit} lower at the paired median`;
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

function exportTable(
  rows: Array<Record<string, string | number | null>>,
  format: "csv" | "excel",
  fileName: string,
  sheetName: string,
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
      : `<?xml version="1.0"?><Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"><Worksheet ss:Name="${escapeXml(sheetName)}"><Table>${[
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
  link.download = `${fileName}.${format === "csv" ? "csv" : "xls"}`;
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
  radiusScorecards,
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
  radiusScorecards: CompetitivePortfolioScorecards["scorecards"] | null;
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
        comparisonMetric:
          row.comparison_metric ??
          row.product_relationships?.[0]?.comparison_metric ??
          "",
        comparisonUnit:
          row.comparison_unit ??
          row.product_relationships?.[0]?.comparison_unit ??
          "",
        medianGrain:
          row.median_grain ?? "scored benchmark product-location observations",
        overall: false,
        pairCount: row.relationships,
        matches: row.scored_product_locations,
        matchedGeographies: row.benchmark_product_locations,
        benchmarkObservedLocations: row.benchmark_observed_locations ?? 0,
        benchmarkScoredLocations: row.benchmark_scored_locations ?? 0,
        benchmarkUnscoredLocations: row.benchmark_unscored_locations ?? 0,
        locationCoverageRate: row.location_coverage_rate ?? null,
        competitorContributingLocations:
          row.competitor_contributing_locations ?? 0,
        competitorContributingStores: row.competitor_contributing_stores ?? 0,
        competitorContributingServiceAreas:
          row.competitor_contributing_service_areas ?? 0,
        benchmarkLowerRate: row.benchmark_lower_rate ?? 0,
        competitorLowerRate: row.competitor_lower_rate ?? 0,
        parityRate: row.parity_rate ?? 0,
        benchmarkMedian: row.benchmark_median,
        competitorMedian: row.competitor_median,
        medianGap: row.paired_median_gap,
        outcome: row.dominant_outcome,
        productRelationships: row.product_relationships ?? [],
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
    const unit = cohort.comparisonUnit || "configured price unit";
    const benchmarkPresentation = cohortPricePresentation(
      cohort.benchmarkMedian,
      cohort.comparisonMetric,
      cohort.comparisonUnit,
      cohort.attributes,
    );
    const competitorPresentation = cohortPricePresentation(
      cohort.competitorMedian,
      cohort.comparisonMetric,
      cohort.comparisonUnit,
      cohort.attributes,
    );
    const gapPresentation = cohortPricePresentation(
      cohort.medianGap,
      cohort.comparisonMetric,
      cohort.comparisonUnit,
      cohort.attributes,
    );
    const benchmarkPackageEquivalent = cohortPackageEquivalent(
      cohort.benchmarkMedian,
      cohort.comparisonMetric,
      cohort.attributes,
    );
    const competitorPackageEquivalent = cohortPackageEquivalent(
      cohort.competitorMedian,
      cohort.comparisonMetric,
      cohort.attributes,
    );
    return {
      Competitor: cohort.competitor,
      Cohort: cohort.segment,
      "Comparison metric": cohort.comparisonMetric,
      "Comparison unit": unit,
      "Median observation grain": cohort.medianGrain,
      "Displayed price basis": benchmarkPresentation.primaryUnitLabel,
      [`${benchmarkName} displayed median`]: benchmarkPresentation.primaryValue,
      [`${cohort.competitor} displayed median`]:
        competitorPresentation.primaryValue,
      "Displayed paired median difference": gapPresentation.primaryValue,
      "Secondary normalized basis": benchmarkPresentation.secondaryUnitLabel,
      [`${benchmarkName} secondary normalized median`]:
        benchmarkPresentation.secondaryValue,
      [`${cohort.competitor} secondary normalized median`]:
        competitorPresentation.secondaryValue,
      "Secondary normalized paired difference": gapPresentation.secondaryValue,
      "Governed product pairs": cohort.pairCount,
      [`${benchmarkName} brand-type mix`]:
        evidence?.benchmarkBrandTypes ?? "unresolved",
      "Competitor brand-type mix":
        evidence?.competitorBrandTypes ?? "unresolved",
      "Paired observations": cohort.matches,
      [`${benchmarkName} stores carrying the cohort`]:
        cohort.benchmarkObservedLocations,
      [`${benchmarkName} stores with a valid local comparison`]:
        cohort.benchmarkScoredLocations,
      "Comparable store coverage": cohort.locationCoverageRate,
      "Contributing competitor stores": cohort.competitorContributingStores,
      "Contributing competitor delivery ZIPs":
        cohort.competitorContributingServiceAreas,
      [`${benchmarkName} lower rate`]: cohort.benchmarkLowerRate,
      "Competitor lower rate": cohort.competitorLowerRate,
      "Parity rate": cohort.parityRate,
      [`${benchmarkName} product-location median (${unit})`]:
        cohort.benchmarkMedian,
      [`${cohort.competitor} selected-local-price median (${unit})`]:
        cohort.competitorMedian,
      [`Paired median difference (${unit})`]: cohort.medianGap,
      [`${benchmarkName} displayed-package equivalent`]:
        benchmarkPackageEquivalent?.value ?? null,
      [`${cohort.competitor} displayed-package equivalent`]:
        competitorPackageEquivalent?.value ?? null,
      "Displayed-package equivalent unit":
        benchmarkPackageEquivalent?.label ??
        competitorPackageEquivalent?.label ??
        null,
    };
  });
  const dimensions = cohortDimensions.length
    ? cohortDimensions.join(" · ")
    : "Product Pack matching attributes";
  const pricePositionRows = (radiusScorecards ?? []).map((scorecard) => ({
    Competitor: scorecard.competitor,
    [`${benchmarkName} stores in scope`]:
      scorecard.benchmark_observed_locations ?? 0,
    [`${benchmarkName} stores with a valid local comparison`]:
      scorecard.benchmark_scored_locations ?? 0,
    "Comparable store coverage": scorecard.location_coverage_rate ?? null,
    "Contributing competitor stores":
      scorecard.competitor_contributing_stores ?? 0,
    "Contributing competitor delivery ZIPs":
      scorecard.competitor_contributing_service_areas ?? 0,
    "Paired product-price comparisons": scorecard.scored_product_locations,
    [`${benchmarkName} lower rate`]: scorecard.benchmark_lower_rate,
    "Competitor lower rate": scorecard.competitor_lower_rate,
    "Parity rate": scorecard.parity_rate,
    "Average competitor minus benchmark": scorecard.average_gap,
  }));
  const cohortCoverage = (radiusScorecards ?? []).map((scorecard) => {
    const cohorted = (radiusCohorts ?? [])
      .filter((cohort) => cohort.competitor_id === scorecard.competitor_id)
      .reduce((total, cohort) => total + cohort.relationships, 0);
    return {
      competitor: scorecard.competitor,
      certified: scorecard.relationships,
      cohorted,
      excluded: Math.max(0, scorecard.relationships - cohorted),
    };
  });

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

  if (!cohorts.length && !radiusScorecards?.length)
    return (
      <section className="cohort-explorer">
        <div className="empty-inline">
          No certified cohort has local comparison evidence under the selected
          retailer, basis, geography, and radius.
        </div>
      </section>
    );

  return (
    <div className="cohort-scorecard-workspace">
      <section className="cohort-view-guide">
        <header>
          <p className="eyebrow">How to read Cohort Scorecards</p>
          <h2>Two levels of the same certified local evidence</h2>
          <p>
            These views are related, but they are not duplicates. Start with
            overall price position, then use the cohort view to understand what
            is producing—or reversing—that result.
          </p>
        </header>
        <div>
          <article>
            <span>1</span>
            <div>
              <h3>Price Position Table</h3>
              <p>
                One retailer-level total across every eligible certified
                product-location in the current competitor, comparison basis,
                geography, and {radiusMiles}-mile radius. It answers: “Who is
                lower overall, and how much evidence supports that conclusion?”
              </p>
            </div>
          </article>
          <article>
            <span>2</span>
            <div>
              <h3>Segment Drivers and Reversals</h3>
              <p>
                The same evidence separated by governed Product Pack attributes.
                It answers: “Which comparable product cohorts create the overall
                result, and which cohorts move in the opposite direction?”
              </p>
            </div>
          </article>
        </div>
        <footer>
          The second view explains the first; its cohort rows should not be
          added together when a product relationship is eligible in more than
          one comparison basis.
        </footer>
      </section>

      <section className="radius-price-position-section">
        <header>
          <div>
            <p className="eyebrow">Overall retailer position</p>
            <h2>Price Position Table</h2>
            <p>
              Retailer-level outcomes at observed {benchmarkName} product-store
              grain. Physical competitors must have eligible evidence within{" "}
              {radiusMiles}
              mile{radiusMiles === 1 ? "" : "s"}; service-area retailers use the
              same delivery ZIP.
            </p>
          </div>
          <div className="cohort-export-actions">
            <button
              type="button"
              onClick={() =>
                exportTable(
                  pricePositionRows,
                  "csv",
                  "competitive-price-position",
                  "Price Position",
                )
              }
            >
              Download CSV
            </button>
            <button
              type="button"
              onClick={() =>
                exportTable(
                  pricePositionRows,
                  "excel",
                  "competitive-price-position",
                  "Price Position",
                )
              }
            >
              Download Excel
            </button>
          </div>
        </header>
        <div className="radius-price-position-table">
          <div className="radius-price-position-head" aria-hidden="true">
            <span>Competitor</span>
            <span>Included products</span>
            <span>Comparable store coverage</span>
            <span>Lower-price share</span>
            <span>Average position</span>
          </div>
          {(radiusScorecards ?? []).map((scorecard) => (
            <article key={scorecard.competitor_id}>
              <div>
                <strong>{scorecard.competitor}</strong>
                <small>
                  {scorecard.relationships.toLocaleString()} certified
                  relationships
                </small>
              </div>
              <div>
                <strong>
                  {scorecard.benchmark_products.toLocaleString()}{" "}
                  {benchmarkName}
                </strong>
                <small>
                  {scorecard.competitor_products.toLocaleString()} competitor
                  products
                </small>
              </div>
              <div>
                <strong>
                  {formatRate(scorecard.location_coverage_rate ?? 0)}
                </strong>
                <small>
                  {(scorecard.benchmark_scored_locations ?? 0).toLocaleString()}{" "}
                  of{" "}
                  {(
                    scorecard.benchmark_observed_locations ?? 0
                  ).toLocaleString()}{" "}
                  {benchmarkName} stores ·{" "}
                  {contributingLocationLabel(
                    scorecard.competitor_contributing_stores ?? 0,
                    scorecard.competitor_contributing_service_areas ?? 0,
                    scorecard.competitor_contributing_locations ?? 0,
                  )}
                </small>
              </div>
              <div>
                <strong>
                  {formatRate(scorecard.benchmark_lower_rate ?? 0)}{" "}
                  {benchmarkName}
                </strong>
                <small>
                  {formatRate(scorecard.competitor_lower_rate ?? 0)} competitor
                  · {formatRate(scorecard.parity_rate ?? 0)} parity
                </small>
              </div>
              <div>
                <strong>
                  {gapCopy(
                    scorecard.average_gap,
                    benchmarkName,
                    scorecard.competitor,
                  ).replace("paired median", "local average")}
                </strong>
                <small>
                  Competitor minus {benchmarkName}:{" "}
                  {formatCurrency(scorecard.average_gap)}
                </small>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="cohort-explorer">
        <header className="cohort-explorer-header">
          <div>
            <p className="eyebrow">Segment drivers and reversals</p>
            <h2>
              Which product cohorts explain—or reverse—the overall position
            </h2>
            <p>
              Each row summarizes certified one-to-one product relationships at
              observed benchmark product-store grain. Physical competitor
              evidence must fall within
              {` ${radiusMiles} mile${radiusMiles === 1 ? "" : "s"}`};
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
        {cohortCoverage.some((row) => row.excluded > 0) ? (
          <div className="empty-inline" role="note">
            Cohort attribute coverage:{" "}
            {cohortCoverage
              .map(
                (row) =>
                  `${row.competitor} ${row.cohorted.toLocaleString()} of ${row.certified.toLocaleString()} certified relationships`,
              )
              .join(" · ")}
            . Relationships missing a complete governed cohort signature remain
            in the retailer total but are not assigned to a cohort row.
          </div>
        ) : null}

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
              onClick={() =>
                exportTable(
                  exportRows,
                  "csv",
                  "competitive-segment-drivers-and-reversals",
                  "Segment Drivers",
                )
              }
            >
              Download CSV
            </button>
            <button
              type="button"
              onClick={() =>
                exportTable(
                  exportRows,
                  "excel",
                  "competitive-segment-drivers-and-reversals",
                  "Segment Drivers",
                )
              }
            >
              Download Excel
            </button>
          </div>
        </div>

        <div className="cohort-list">
          {visible.map((cohort) => {
            const limited = cohort.matches < minimumGeographies;
            const evidence = pairEvidence[cohort.id];
            const benchmarkPresentation = cohortPricePresentation(
              cohort.benchmarkMedian,
              cohort.comparisonMetric,
              cohort.comparisonUnit,
              cohort.attributes,
            );
            const competitorPresentation = cohortPricePresentation(
              cohort.competitorMedian,
              cohort.comparisonMetric,
              cohort.comparisonUnit,
              cohort.attributes,
            );
            const gapPresentation = cohortPricePresentation(
              cohort.medianGap,
              cohort.comparisonMetric,
              cohort.comparisonUnit,
              cohort.attributes,
            );
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
                    {formatRate(cohort.locationCoverageRate ?? 0)} store
                    coverage ·{" "}
                    {cohort.benchmarkScoredLocations.toLocaleString()} of{" "}
                    {cohort.benchmarkObservedLocations.toLocaleString()}{" "}
                    {benchmarkName} stores ·{" "}
                    {contributingLocationLabel(
                      cohort.competitorContributingStores,
                      cohort.competitorContributingServiceAreas,
                      cohort.competitorContributingLocations,
                    )}
                  </p>
                  <div className="cohort-pair-evidence">
                    <strong>
                      {cohort.pairCount.toLocaleString()} governed product pairs
                    </strong>
                    <span>
                      {benchmarkName}:{" "}
                      {evidence?.benchmarkBrandTypes ?? "brand type unresolved"}
                    </span>
                    <span>
                      {cohort.competitor}:{" "}
                      {evidence?.competitorBrandTypes ??
                        "brand type unresolved"}
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
                    {gapCopy(
                      gapPresentation.primaryValue,
                      benchmarkName,
                      cohort.competitor,
                      gapPresentation.primaryUnitLabel,
                    )}
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
                <div className="cohort-median-column">
                  <dl className="cohort-medians">
                    <div>
                      <dt>{benchmarkName} product-location median</dt>
                      <dd>
                        {formatCohortCurrency(
                          benchmarkPresentation.primaryValue,
                          benchmarkPresentation.primaryUnitLabel,
                        )}{" "}
                        <small>{benchmarkPresentation.primaryUnitLabel}</small>
                      </dd>
                      {benchmarkPresentation.secondaryValue !== null ? (
                        <small>
                          {formatCohortCurrency(
                            benchmarkPresentation.secondaryValue,
                            benchmarkPresentation.secondaryUnitLabel ?? "",
                          )}{" "}
                          {benchmarkPresentation.secondaryUnitLabel}
                        </small>
                      ) : null}
                    </div>
                    <div>
                      <dt>{cohort.competitor} selected-local-price median</dt>
                      <dd>
                        {formatCohortCurrency(
                          competitorPresentation.primaryValue,
                          competitorPresentation.primaryUnitLabel,
                        )}{" "}
                        <small>{competitorPresentation.primaryUnitLabel}</small>
                      </dd>
                      {competitorPresentation.secondaryValue !== null ? (
                        <small>
                          {formatCohortCurrency(
                            competitorPresentation.secondaryValue,
                            competitorPresentation.secondaryUnitLabel ?? "",
                          )}{" "}
                          {competitorPresentation.secondaryUnitLabel}
                        </small>
                      ) : null}
                    </div>
                  </dl>
                  <small className="cohort-median-definition">
                    Based on {cohort.matches.toLocaleString()} paired local
                    product-price comparisons.
                    {benchmarkPresentation.secondaryUnitLabel
                      ? ` The fixed ${benchmarkPresentation.primaryUnitLabel.replace("per ", "")} is shown first; ${benchmarkPresentation.secondaryUnitLabel} is secondary context.`
                      : ` Displayed ${benchmarkPresentation.primaryUnitLabel}.`}
                  </small>
                </div>
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
                Choose another outcome filter while keeping the current
                competitor and lens.
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
          certified relationships into product-location outcomes before this
          page receives rates or medians; the browser does not recalculate them.
        </footer>
      </section>
    </div>
  );
}
