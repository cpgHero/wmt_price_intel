import type { RetailCompetitiveIntelligenceCanonicalReportDataset } from "@rci/contracts";

type CanonicalDataset = RetailCompetitiveIntelligenceCanonicalReportDataset;
export type CanonicalProductRelationship =
  CanonicalDataset["product_relationships"][number];
export type CanonicalOutcome =
  CanonicalProductRelationship["comparison"]["outcome"];
export type CanonicalBrandType =
  CanonicalProductRelationship["benchmark_product"]["brand_type"];

export const BROAD_WALMART_DISTRIBUTION_THRESHOLD = 1_000;

export type CanonicalRelationshipSort =
  "action_priority" | "distribution_desc" | "gap_desc" | "title_asc";

export interface CanonicalRelationshipFilters {
  query: string;
  outcome: CanonicalOutcome | "all";
  brandType: CanonicalBrandType | "all";
  competitorRetailerId: string | "all";
  minimumWalmartDistribution: number;
  sort: CanonicalRelationshipSort;
}

export const DEFAULT_CANONICAL_RELATIONSHIP_FILTERS: CanonicalRelationshipFilters =
  {
    query: "",
    outcome: "all",
    brandType: "all",
    competitorRetailerId: "all",
    minimumWalmartDistribution: 0,
    sort: "action_priority",
  };

function normalizedText(value: unknown) {
  return String(value ?? "")
    .toLocaleLowerCase("en-US")
    .replace(/\s+/g, " ")
    .trim();
}

function walmartDistribution(relationship: CanonicalProductRelationship) {
  return relationship.benchmark_product.distribution
    .physical_store_distribution_count;
}

function absoluteGap(relationship: CanonicalProductRelationship) {
  return Math.abs(relationship.comparison.price_delta_percent);
}

function titleCompare(
  left: CanonicalProductRelationship,
  right: CanonicalProductRelationship,
) {
  return left.benchmark_product.title.localeCompare(
    right.benchmark_product.title,
    "en-US",
  );
}

function outcomePriority(outcome: CanonicalOutcome) {
  if (outcome === "competitor_wins") return 0;
  if (outcome === "walmart_wins") return 1;
  if (outcome === "parity") return 2;
  return 3;
}

export function relationshipSearchText(
  relationship: CanonicalProductRelationship,
) {
  return normalizedText(
    [
      relationship.relationship_id,
      relationship.benchmark_product.retailer_product_id,
      relationship.benchmark_product.title,
      relationship.benchmark_product.brand,
      relationship.benchmark_product.brand_type,
      relationship.competitor_product.retailer_id,
      relationship.competitor_product.retailer_product_id,
      relationship.competitor_product.title,
      relationship.competitor_product.brand,
      relationship.comparison.outcome,
      relationship.comparison.comparison_basis,
    ].join(" "),
  );
}

export function sortCanonicalRelationships(
  relationships: CanonicalProductRelationship[],
  sort: CanonicalRelationshipSort,
) {
  return [...relationships].sort((left, right) => {
    if (sort === "title_asc") return titleCompare(left, right);
    if (sort === "gap_desc") {
      return (
        absoluteGap(right) - absoluteGap(left) || titleCompare(left, right)
      );
    }
    if (sort === "distribution_desc") {
      return (
        walmartDistribution(right) - walmartDistribution(left) ||
        absoluteGap(right) - absoluteGap(left) ||
        titleCompare(left, right)
      );
    }
    return (
      outcomePriority(left.comparison.outcome) -
        outcomePriority(right.comparison.outcome) ||
      walmartDistribution(right) - walmartDistribution(left) ||
      absoluteGap(right) - absoluteGap(left) ||
      titleCompare(left, right)
    );
  });
}

export function filterCanonicalRelationships(
  relationships: CanonicalProductRelationship[],
  filters: CanonicalRelationshipFilters,
) {
  const query = normalizedText(filters.query);
  return sortCanonicalRelationships(
    relationships.filter((relationship) => {
      if (
        filters.outcome !== "all" &&
        relationship.comparison.outcome !== filters.outcome
      ) {
        return false;
      }
      if (
        filters.brandType !== "all" &&
        relationship.benchmark_product.brand_type !== filters.brandType
      ) {
        return false;
      }
      if (
        filters.competitorRetailerId !== "all" &&
        relationship.competitor_product.retailer_id !==
          filters.competitorRetailerId
      ) {
        return false;
      }
      if (
        walmartDistribution(relationship) < filters.minimumWalmartDistribution
      ) {
        return false;
      }
      if (query && !relationshipSearchText(relationship).includes(query)) {
        return false;
      }
      return true;
    }),
    filters.sort,
  );
}

export function groupCanonicalRelationshipsByOutcome(
  relationships: CanonicalProductRelationship[],
) {
  return {
    walmartLosses: relationships.filter(
      (row) => row.comparison.outcome === "competitor_wins",
    ),
    walmartWins: relationships.filter(
      (row) => row.comparison.outcome === "walmart_wins",
    ),
    parity: relationships.filter(
      (row) =>
        row.comparison.outcome === "parity" ||
        row.comparison.outcome === "unscored",
    ),
  };
}

export function canonicalCompetitorOptions(
  relationships: CanonicalProductRelationship[],
) {
  return Array.from(
    new Map(
      relationships.map((relationship) => [
        relationship.competitor_product.retailer_id,
        relationship.competitor_product.retailer_id,
      ]),
    ).values(),
  ).sort((left, right) => left.localeCompare(right, "en-US"));
}

export function summarizeCanonicalBrandTypes(
  relationships: CanonicalProductRelationship[],
) {
  const summaries = new Map<
    CanonicalBrandType,
    {
      brandType: CanonicalBrandType;
      broadWalmartLosses: number;
      relationships: number;
      walmartLosses: number;
      walmartWins: number;
    }
  >();
  for (const relationship of relationships) {
    const brandType = relationship.benchmark_product.brand_type;
    const summary =
      summaries.get(brandType) ??
      ({
        brandType,
        broadWalmartLosses: 0,
        relationships: 0,
        walmartLosses: 0,
        walmartWins: 0,
      } as const);
    const next = { ...summary, relationships: summary.relationships + 1 };
    if (relationship.comparison.outcome === "competitor_wins") {
      next.walmartLosses += 1;
      if (
        walmartDistribution(relationship) >=
        BROAD_WALMART_DISTRIBUTION_THRESHOLD
      ) {
        next.broadWalmartLosses += 1;
      }
    }
    if (relationship.comparison.outcome === "walmart_wins") {
      next.walmartWins += 1;
    }
    summaries.set(brandType, next);
  }
  return Array.from(summaries.values()).sort((left, right) => {
    const order: CanonicalBrandType[] = [
      "private_label",
      "national",
      "regional",
      "unclassified",
    ];
    return order.indexOf(left.brandType) - order.indexOf(right.brandType);
  });
}
