"use client";

import { useMemo, useState } from "react";

import type { JsonObject } from "@/lib/api";
import {
  comparableCohorts,
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

export function ComparableCohortExplorer({
  records,
  benchmarkName,
  cohortDimensions,
  minimumGeographies,
  ambiguousMatches,
  onReviewMatches,
  onOpenCohort,
  pairEvidence,
}: Readonly<{
  records: JsonObject[];
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
}>) {
  const [outcome, setOutcome] = useState<OutcomeFilter>("all");
  const [sort, setSort] = useState<CohortSort>("evidence");
  const [showAll, setShowAll] = useState(false);
  const cohorts = useMemo(() => comparableCohorts(records), [records]);
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
  const dimensions = cohortDimensions.length
    ? cohortDimensions.join(" · ")
    : "Product Pack matching attributes";

  if (!cohorts.length) return null;

  return (
    <section className="cohort-explorer">
      <header className="cohort-explorer-header">
        <div>
          <p className="eyebrow">Comparable cohort explorer</p>
          <h2>Category rollups without weakening item-level match integrity</h2>
          <p>
            Each row summarizes persisted one-to-one store comparisons inside a
            Product Pack cohort. Products contribute to a rollup; they do not
            become one-to-many matches.
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
      </div>

      <div className="cohort-list">
        {visible.map((cohort) => {
          const limited = cohort.matchedGeographies < minimumGeographies;
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
                  {cohort.matches.toLocaleString()} paired location observations
                  · {cohort.matchedGeographies.toLocaleString()} legacy
                  exact-ZIP markets
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
                    ? `Directional · below ${minimumGeographies} market threshold`
                    : "Decision-grade market breadth"}
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
        Search supplies store-specific price and location. Cohort rates and
        medians are projected from the immutable AnalysisResult; this view does
        not recalculate them.
      </footer>
    </section>
  );
}
