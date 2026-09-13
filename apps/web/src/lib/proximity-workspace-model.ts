import type { LocationRetailer, ProximityView } from "./api";

export type ComparisonScope = "all-walmart" | "competitor-footprint";

function uniqueSortedStates(values: Array<string | null | undefined>) {
  return [...new Set(values.map((value) => value || "").filter(Boolean))].sort(
    (left, right) => left.localeCompare(right),
  );
}

export function competitorFootprintStatesForView(view: ProximityView | null) {
  return uniqueSortedStates(
    (view?.competitor_pairs ?? []).map((pair) => pair.competitor.state),
  );
}

export function recommendedComparisonScopeForStateCounts(
  competitorStateCount: number,
  benchmarkStateCount: number,
): ComparisonScope {
  if (!competitorStateCount || !benchmarkStateCount) return "all-walmart";
  const regionalStateThreshold = Math.min(
    10,
    Math.max(1, Math.floor(benchmarkStateCount * 0.25)),
  );
  return competitorStateCount <= regionalStateThreshold
    ? "competitor-footprint"
    : "all-walmart";
}

export function recommendedScopeForView(
  view: ProximityView | null,
): ComparisonScope {
  const competitorStateCount = competitorFootprintStatesForView(view).length;
  const benchmarkStateCount = (view?.state_options ?? []).filter(
    Boolean,
  ).length;
  return recommendedComparisonScopeForStateCounts(
    competitorStateCount,
    benchmarkStateCount,
  );
}

export function selectCompetitorForProximityLoad({
  competitorOptions,
  countryChanged,
  currentCompetitorRetailerId,
  requestedCompetitorRetailerId,
}: {
  competitorOptions: LocationRetailer[];
  countryChanged: boolean;
  currentCompetitorRetailerId: string;
  requestedCompetitorRetailerId?: string;
}) {
  const requestedCompetitor =
    requestedCompetitorRetailerId ??
    (countryChanged ? "" : currentCompetitorRetailerId);
  return requestedCompetitor &&
    competitorOptions.some((retailer) => retailer.id === requestedCompetitor)
    ? requestedCompetitor
    : competitorOptions[0]?.id || "";
}
