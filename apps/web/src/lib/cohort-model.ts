import type { JsonObject } from "./api";

export type CohortOutcome =
  "benchmark_lower" | "competitor_lower" | "parity" | "unavailable";

export type CohortSort = "evidence" | "competitor_pressure" | "gap";

export interface ComparableCohort {
  id: string;
  competitorId: string;
  competitor: string;
  profileId: string;
  segmentId: string;
  segment: string;
  matches: number;
  matchedGeographies: number;
  benchmarkLowerRate: number;
  competitorLowerRate: number;
  parityRate: number;
  benchmarkMedian: number | null;
  competitorMedian: number | null;
  medianGap: number | null;
  outcome: CohortOutcome;
}

function numericValue(row: JsonObject, rawKey: string, displayKey: string) {
  const raw = row[rawKey];
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  const display = row[displayKey];
  if (typeof display === "number" && Number.isFinite(display)) return display;
  if (typeof display !== "string") return null;
  const percent = display.includes("%");
  const parsed = Number(display.replaceAll(",", "").replace(/[^0-9.-]/g, ""));
  if (!Number.isFinite(parsed)) return null;
  return percent ? parsed / 100 : parsed;
}

function outcomeValue(value: unknown): CohortOutcome {
  const token = String(value ?? "")
    .trim()
    .toLowerCase()
    .replaceAll(" ", "_");
  if (
    token === "benchmark_lower" ||
    token === "competitor_lower" ||
    token === "parity"
  )
    return token;
  return "unavailable";
}

export function comparableCohorts(records: JsonObject[]): ComparableCohort[] {
  return records.flatMap((row) => {
    const segment = String(row.segment ?? "").trim();
    if (!segment || segment === "All comparable items") return [];
    const competitor = String(row.competitor ?? "Competitor");
    const competitorId = String(row._competitor_id ?? competitor);
    const profileId = String(row._profile_id ?? "");
    const segmentId = String(row._segment_id ?? segment);
    return [
      {
        id: `${competitorId}:${profileId}:${segmentId}`,
        competitorId,
        competitor,
        profileId,
        segmentId,
        segment,
        matches: numericValue(row, "_matches", "matches") ?? 0,
        matchedGeographies:
          numericValue(row, "_matched_geographies", "matched geographies") ?? 0,
        benchmarkLowerRate:
          numericValue(row, "_benchmark_lower_rate", "benchmark lower") ?? 0,
        competitorLowerRate:
          numericValue(row, "_competitor_lower_rate", "competitor lower") ?? 0,
        parityRate: numericValue(row, "_parity_rate", "parity") ?? 0,
        benchmarkMedian: numericValue(
          row,
          "_benchmark_median",
          "benchmark median",
        ),
        competitorMedian: numericValue(
          row,
          "_competitor_median",
          "competitor median",
        ),
        medianGap: numericValue(
          row,
          "_median_gap",
          "competitor - benchmark gap",
        ),
        outcome: outcomeValue(row._dominant_outcome ?? row["dominant outcome"]),
      },
    ];
  });
}

export function sortComparableCohorts(
  cohorts: ComparableCohort[],
  sort: CohortSort,
) {
  return [...cohorts].sort((left, right) => {
    if (sort === "competitor_pressure") {
      return (
        right.competitorLowerRate - left.competitorLowerRate ||
        right.matchedGeographies - left.matchedGeographies ||
        left.segment.localeCompare(right.segment)
      );
    }
    if (sort === "gap") {
      return (
        Math.abs(right.medianGap ?? 0) - Math.abs(left.medianGap ?? 0) ||
        right.matchedGeographies - left.matchedGeographies ||
        left.segment.localeCompare(right.segment)
      );
    }
    return (
      right.matchedGeographies - left.matchedGeographies ||
      right.matches - left.matches ||
      left.segment.localeCompare(right.segment)
    );
  });
}
