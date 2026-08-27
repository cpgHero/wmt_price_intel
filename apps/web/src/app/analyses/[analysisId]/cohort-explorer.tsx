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
        overall: false,
        pairCount: row.relationships,
        matches: row.scored_product_locations,
        matchedGeographies: row.benchmark_product_locations,
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
    return {
      Competitor: cohort.competitor,
      Cohort: cohort.segment,
      "Governed product pairs": cohort.pairCount,
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
  const pricePositionRows = (radiusScorecards ?? []).map((scorecard) => ({
    Competitor: scorecard.competitor,
    "Certified relationships": scorecard.relationships,
    [`${benchmarkName} products`]: scorecard.benchmark_products,
    "Competitor products": scorecard.competitor_products,
    "Observed benchmark product-locations":
      scorecard.benchmark_product_locations,
    [`Scored product-locations within ${radiusMiles} miles`]:
      scorecard.scored_product_locations,
    "Local coverage rate": scorecard.coverage_rate,
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
            <span>Local evidence</span>
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
                  {scorecard.scored_product_locations.toLocaleString()} of{" "}
                  {scorecard.benchmark_product_locations.toLocaleString()}
                </strong>
                <small>
                  {formatRate(scorecard.coverage_rate ?? 0)} local coverage
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
                      cohort.medianGap,
                      benchmarkName,
                      cohort.competitor,
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
