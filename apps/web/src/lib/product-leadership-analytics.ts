import type { CompetitiveProductLeadership } from "./api";

type Outcome = CompetitiveProductLeadership["outcomes"][number];
type Relationship = CompetitiveProductLeadership["relationships"][number];
type GeographySummary = CompetitiveProductLeadership["state_summaries"][number];

export interface MatchGroupSummary {
  relationships: number;
  competitorProducts: number;
  competitorRetailers: number;
  globalRelationships: number;
  locationScopedRelationships: number;
  relationshipsWithEvidence: number;
}

export interface RelationshipEvidence extends Relationship {
  benchmarkLocations: number;
  benchmarkProductName: string;
  competitorProductName: string;
  competitorBrand: string | null;
  competitorBrandType: Outcome["benchmark"]["brand_type"];
  competitorImageUrl: string | null;
}

export interface LeadershipException {
  id: string;
  priority: "high" | "medium" | "review";
  type: "competitor_undercut" | "narrow_lead" | "insufficient_evidence";
  label: string;
  reason: string;
  outcome: Outcome;
}

export interface MarketPerformance extends GeographySummary {
  scoredRate: number | null;
  lossRate: number | null;
}

export function summarizeMatchGroup(
  relationships: Relationship[],
  outcomes: Outcome[],
): MatchGroupSummary {
  const observedRelationships = new Set(
    outcomes
      .map((row) => row.relationship_id)
      .filter((value): value is string => Boolean(value)),
  );
  return {
    relationships: relationships.length,
    competitorProducts: new Set(
      relationships.map(
        (row) => `${row.competitor_id}:${row.competitor_product_id}`,
      ),
    ).size,
    competitorRetailers: new Set(relationships.map((row) => row.competitor_id))
      .size,
    globalRelationships: relationships.filter(
      (row) => row.scope_mode === "global",
    ).length,
    locationScopedRelationships: relationships.filter(
      (row) => row.scope_mode !== "global",
    ).length,
    relationshipsWithEvidence: relationships.filter((row) =>
      observedRelationships.has(row.relationship_id),
    ).length,
  };
}

export function relationshipEvidence(
  relationships: Relationship[],
  outcomes: Outcome[],
): RelationshipEvidence[] {
  return relationships.map((relationship) => {
    const evidence = outcomes.filter(
      (row) => row.relationship_id === relationship.relationship_id,
    );
    const sample = evidence.find((row) => row.competitor)?.competitor ?? null;
    return {
      ...relationship,
      benchmarkLocations: evidence.length,
      benchmarkProductName:
        evidence[0]?.benchmark.product_name ??
        relationship.benchmark_product_id,
      competitorProductName:
        sample?.product_name ?? relationship.competitor_product_id,
      competitorBrand: sample?.brand ?? null,
      competitorBrandType: sample?.brand_type ?? "unclassified",
      competitorImageUrl: sample?.image_url ?? null,
    };
  });
}

export function leadershipExceptions(
  outcomes: Outcome[],
): LeadershipException[] {
  return outcomes
    .filter((row) => ["losing", "at_risk", "unscored"].includes(row.status))
    .map((outcome) => {
      if (outcome.status === "losing") {
        return {
          id: outcome.id,
          priority: "high" as const,
          type: "competitor_undercut" as const,
          label: "Competitor undercut",
          reason: outcome.competitor
            ? `${outcome.competitor.retailer_name} is lower at this benchmark store.`
            : "A governed competitor is lower at this benchmark store.",
          outcome,
        };
      }
      if (outcome.status === "at_risk") {
        return {
          id: outcome.id,
          priority: "medium" as const,
          type: "narrow_lead" as const,
          label: "Narrow benchmark lead",
          reason:
            "The benchmark is lower, but its lead is inside the governed at-risk threshold.",
          outcome,
        };
      }
      return {
        id: outcome.id,
        priority: "review" as const,
        type: "insufficient_evidence" as const,
        label: "Insufficient comparable evidence",
        reason:
          "No current governed competitor observation is geographically comparable.",
        outcome,
      };
    })
    .sort((left, right) => {
      const priority = { high: 0, medium: 1, review: 2 } as const;
      const priorityOrder = priority[left.priority] - priority[right.priority];
      if (priorityOrder) return priorityOrder;
      return (
        (right.outcome.comparison_value_reduction_to_lead ?? 0) -
        (left.outcome.comparison_value_reduction_to_lead ?? 0)
      );
    });
}

export function marketPerformance(
  rows: GeographySummary[],
): MarketPerformance[] {
  return rows
    .map((row) => ({
      ...row,
      scoredRate:
        row.benchmark_observed_stores > 0
          ? row.scored_stores / row.benchmark_observed_stores
          : null,
      lossRate:
        row.scored_stores > 0 ? row.losing_stores / row.scored_stores : null,
    }))
    .sort((left, right) => {
      const leftRate = left.lossRate ?? -1;
      const rightRate = right.lossRate ?? -1;
      return rightRate - leftRate || right.losing_stores - left.losing_stores;
    });
}

export function freshestObservation(outcomes: Outcome[]): string | null {
  const values = outcomes
    .flatMap((row) => [row.benchmark.observed_at, row.competitor?.observed_at])
    .filter((value): value is string => Boolean(value))
    .sort();
  return values.at(-1) ?? null;
}
