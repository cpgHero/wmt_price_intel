import type {
  MatchReview,
  MatchReviewConnection,
  MatchReviewProduct,
} from "@/lib/api";

export interface MatchReviewScope {
  connections: MatchReviewConnection[];
  benchmarkProducts: MatchReviewProduct[];
  competitorProducts: MatchReviewProduct[];
  unmatchedBenchmarkProducts: MatchReviewProduct[];
  unmatchedCompetitorProducts: MatchReviewProduct[];
  confirmedOutsideProfile: MatchReviewConnection[];
  crossLensMemberships: Record<string, CrossLensMembership[]>;
  summary: {
    suggested: number;
    confirmed: number;
    rejected: number;
    ambiguous: number;
    unmatched: number;
  };
}

export interface CrossLensMembership {
  profileId: string;
  profileLabel: string;
  status: MatchReviewConnection["status"];
  counterpartProductId: string;
}

export interface ProductDetailRow {
  section: string;
  label: string;
  value: string;
}

export function evidenceForProfile(
  connection: MatchReviewConnection,
  profileId: string,
) {
  return connection.profile_evidence.find(
    (evidence) => evidence.profile_id === profileId,
  );
}

export function scopeMatchReview(
  review: MatchReview,
  competitorId: string,
  profileId: string,
): MatchReviewScope {
  const benchmarkProducts = review.products.filter(
    (product) => product.retailer_id === review.benchmark_retailer.id,
  );
  const competitorProducts = review.products.filter(
    (product) => product.retailer_id === competitorId,
  );
  const connections = review.connections.filter(
    (connection) =>
      connection.competitor_retailer_id === competitorId &&
      connection.eligible_profile_ids.includes(profileId),
  );
  const confirmedOutsideProfile = review.connections.filter(
    (connection) =>
      connection.competitor_retailer_id === competitorId &&
      connection.status === "confirmed" &&
      !connection.eligible_profile_ids.includes(profileId),
  );
  const crossLensMemberships: Record<string, CrossLensMembership[]> = {};
  const addCrossLensMembership = (
    key: string,
    membership: CrossLensMembership,
  ) => {
    const memberships = (crossLensMemberships[key] ||= []);
    const existing = memberships.find(
      (candidate) => candidate.profileId === membership.profileId,
    );
    if (!existing) {
      memberships.push(membership);
      return;
    }
    if (membership.status === "confirmed" && existing.status !== "confirmed") {
      Object.assign(existing, membership);
    }
  };
  for (const connection of review.connections) {
    if (
      connection.competitor_retailer_id !== competitorId ||
      connection.status === "rejected" ||
      connection.eligible_profile_ids.includes(profileId)
    )
      continue;
    for (const otherProfileId of connection.eligible_profile_ids) {
      const membership = {
        profileId: otherProfileId,
        profileLabel:
          review.profiles.find((profile) => profile.id === otherProfileId)
            ?.label || otherProfileId,
        status: connection.status,
        counterpartProductId: connection.competitor_product_id,
      } satisfies CrossLensMembership;
      const benchmarkKey = `${review.benchmark_retailer.id}:${connection.benchmark_product_id}`;
      addCrossLensMembership(benchmarkKey, membership);
      const competitorKey = `${competitorId}:${connection.competitor_product_id}`;
      addCrossLensMembership(competitorKey, {
        ...membership,
        counterpartProductId: connection.benchmark_product_id,
      });
    }
  }
  const active = connections.filter(
    (connection) => connection.status !== "rejected",
  );
  const connectedBenchmark = new Set(
    [...active, ...confirmedOutsideProfile].map(
      (connection) => connection.benchmark_product_id,
    ),
  );
  const connectedCompetitor = new Set(
    [...active, ...confirmedOutsideProfile].map(
      (connection) => connection.competitor_product_id,
    ),
  );
  const unmatchedBenchmarkProducts = benchmarkProducts.filter(
    (product) => !connectedBenchmark.has(product.product_id),
  );
  const unmatchedCompetitorProducts = competitorProducts.filter(
    (product) => !connectedCompetitor.has(product.product_id),
  );

  return {
    connections,
    benchmarkProducts,
    competitorProducts,
    unmatchedBenchmarkProducts,
    unmatchedCompetitorProducts,
    confirmedOutsideProfile,
    crossLensMemberships,
    summary: {
      suggested: connections.filter(
        (connection) => connection.status === "suggested",
      ).length,
      confirmed: connections.filter(
        (connection) => connection.status === "confirmed",
      ).length,
      rejected: connections.filter(
        (connection) => connection.status === "rejected",
      ).length,
      ambiguous: connections.filter(
        (connection) => connection.status === "ambiguous",
      ).length,
      unmatched:
        unmatchedBenchmarkProducts.length + unmatchedCompetitorProducts.length,
    },
  };
}

function humanize(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function displayValue(value: unknown): string | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean")
    return String(value);
  if (Array.isArray(value)) {
    const values = value
      .map((item) => {
        if (typeof item === "string" || typeof item === "number")
          return String(item);
        if (item && typeof item === "object" && "name" in item)
          return String(item.name);
        return null;
      })
      .filter((item): item is string => Boolean(item));
    return values.length ? values.join(" › ") : null;
  }
  return null;
}

export function productDetailRows(
  product: MatchReviewProduct,
): ProductDetailRow[] {
  const rows: ProductDetailRow[] = [];
  const sections = [
    ["Identifiers", product.identifiers],
    ["Specifications", product.specification],
    ["Physical properties", product.physical_properties],
    ["Variant", product.variant_configuration],
  ] as const;
  const category = displayValue(product.category_path);
  if (category)
    rows.push({ section: "Product", label: "Category", value: category });
  for (const [section, candidate] of sections) {
    if (!candidate || typeof candidate !== "object" || Array.isArray(candidate))
      continue;
    for (const [label, rawValue] of Object.entries(candidate)) {
      const value = displayValue(rawValue);
      if (value) rows.push({ section, label: humanize(label), value });
    }
  }
  return rows;
}

export function connectionSearchText(
  connection: MatchReviewConnection,
  benchmark: MatchReviewProduct | undefined,
  competitor: MatchReviewProduct | undefined,
) {
  return [
    connection.benchmark_product_id,
    connection.competitor_product_id,
    benchmark?.name,
    benchmark?.brand,
    competitor?.name,
    competitor?.brand,
    connection.reason,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}
