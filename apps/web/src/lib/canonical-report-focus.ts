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

export type CanonicalPriceBasis =
  "comparison_unit_price" | "package_price" | "mixed_price_basis";

export interface CanonicalRelationshipFilters {
  query: string;
  outcome: CanonicalOutcome | "all";
  brandType: CanonicalBrandType | "all";
  benchmarkBrand: string | "all";
  competitorBrand: string | "all";
  competitorRetailerId: string | "all";
  comparisonBasis: string | "all";
  unitBasis: string | "all";
  priceBasis: CanonicalPriceBasis | "all";
  minimumWalmartDistribution: number;
  sort: CanonicalRelationshipSort;
}

export const DEFAULT_CANONICAL_RELATIONSHIP_FILTERS: CanonicalRelationshipFilters =
  {
    query: "",
    outcome: "all",
    brandType: "all",
    benchmarkBrand: "all",
    competitorBrand: "all",
    competitorRetailerId: "all",
    comparisonBasis: "all",
    unitBasis: "all",
    priceBasis: "all",
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

function canonicalPriceBasisForProduct(
  product:
    | CanonicalProductRelationship["benchmark_product"]
    | CanonicalProductRelationship["competitor_product"],
) {
  if (
    typeof product.price.package_price === "number" &&
    Number.isFinite(product.price.package_price) &&
    product.price.package_price > 0
  ) {
    return "package_price" as const;
  }
  return "comparison_unit_price" as const;
}

export function canonicalRelationshipPriceBasis(
  relationship: CanonicalProductRelationship,
): CanonicalPriceBasis {
  const benchmarkBasis = canonicalPriceBasisForProduct(
    relationship.benchmark_product,
  );
  const competitorBasis = canonicalPriceBasisForProduct(
    relationship.competitor_product,
  );
  return benchmarkBasis === competitorBasis
    ? benchmarkBasis
    : "mixed_price_basis";
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
      relationship.comparison.unit_basis,
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
        filters.benchmarkBrand !== "all" &&
        normalizedText(relationship.benchmark_product.brand) !==
          normalizedText(filters.benchmarkBrand)
      ) {
        return false;
      }
      if (
        filters.competitorBrand !== "all" &&
        normalizedText(relationship.competitor_product.brand) !==
          normalizedText(filters.competitorBrand)
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
        filters.comparisonBasis !== "all" &&
        relationship.comparison.comparison_basis !== filters.comparisonBasis
      ) {
        return false;
      }
      if (
        filters.unitBasis !== "all" &&
        relationship.comparison.unit_basis !== filters.unitBasis
      ) {
        return false;
      }
      if (
        filters.priceBasis !== "all" &&
        canonicalRelationshipPriceBasis(relationship) !== filters.priceBasis
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

function distinctSorted(values: Array<string | null | undefined>) {
  return Array.from(
    new Set(values.filter((value): value is string => Boolean(value?.trim()))),
  ).sort((left, right) => left.localeCompare(right, "en-US"));
}

export function canonicalBenchmarkBrandOptions(
  relationships: CanonicalProductRelationship[],
) {
  return distinctSorted(
    relationships.map((relationship) => relationship.benchmark_product.brand),
  );
}

export function canonicalCompetitorBrandOptions(
  relationships: CanonicalProductRelationship[],
) {
  return distinctSorted(
    relationships.map((relationship) => relationship.competitor_product.brand),
  );
}

export function canonicalComparisonBasisOptions(
  relationships: CanonicalProductRelationship[],
) {
  return distinctSorted(
    relationships.map(
      (relationship) => relationship.comparison.comparison_basis,
    ),
  );
}

export function canonicalUnitBasisOptions(
  relationships: CanonicalProductRelationship[],
) {
  return distinctSorted(
    relationships.map((relationship) => relationship.comparison.unit_basis),
  );
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
