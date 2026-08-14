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

export interface ProductEvidenceSummary {
  enriched: boolean;
  description: string | null;
  seller: string | null;
  category: string | null;
  condition: string | null;
  rating: number | null;
  reviewCount: number | null;
  demand: string | null;
  fulfillment: string[];
  imageCount: number;
  videoCount: number;
  relationshipCount: number;
  sourceFieldCount: number;
  unmappedFields: string[];
}

export interface ProductComparisonRow extends ProductDetailRow {
  counterpartValue: string | null;
  status: "aligned" | "different" | "missing";
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
      connection.status === "rejected"
    )
      continue;
    const isScopedConfirmed =
      connection.status === "confirmed" &&
      connection.scope != null &&
      connection.scope.mode !== "global";
    if (
      connection.eligible_profile_ids.includes(profileId) &&
      !isScopedConfirmed
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
  const locksEveryLocation = (connection: MatchReviewConnection) =>
    connection.status !== "confirmed" ||
    connection.scope == null ||
    connection.scope.mode === "global";
  const connectedBenchmark = new Set(
    [...active, ...confirmedOutsideProfile]
      .filter(locksEveryLocation)
      .map((connection) => connection.benchmark_product_id),
  );
  const connectedCompetitor = new Set(
    [...active, ...confirmedOutsideProfile]
      .filter(locksEveryLocation)
      .map((connection) => connection.competitor_product_id),
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
  if (typeof value === "number") return String(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
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

function recordValue(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function arrayCount(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

export function productEvidenceSummary(
  product: MatchReviewProduct,
): ProductEvidenceSummary {
  const fulfillment = recordValue(product.fulfillment);
  const reviews = recordValue(product.reviews);
  const demand = recordValue(product.demand);
  const content = recordValue(product.content);
  const relationships = recordValue(product.relationships);
  const media = recordValue(product.media);
  const sourceFields = Array.isArray(product.pdp_source_field_inventory)
    ? product.pdp_source_field_inventory.filter(
        (value): value is string => typeof value === "string",
      )
    : [];
  const unmappedFields = Array.isArray(product.pdp_unmapped_source_fields)
    ? product.pdp_unmapped_source_fields.filter(
        (value): value is string => typeof value === "string",
      )
    : [];
  const fulfillmentLabels: string[] = [];
  const pickup = fulfillment.pickup_available;
  if (typeof pickup === "boolean")
    fulfillmentLabels.push(`Pickup ${pickup ? "available" : "unavailable"}`);
  const shipping = displayValue(fulfillment.shipping_type);
  if (shipping) fulfillmentLabels.push(`Shipping: ${shipping}`);
  const fulfilledByRetailer = fulfillment.fulfilled_by_retailer;
  if (typeof fulfilledByRetailer === "boolean")
    fulfillmentLabels.push(
      fulfilledByRetailer ? "Retailer fulfilled" : "Fulfillment not confirmed",
    );
  const monthlySales = numberValue(demand.monthly_sales_volume);
  const weeklySales = numberValue(demand.weekly_sales_volume);
  const imageCount =
    arrayCount(media.images) ||
    (displayValue(media.image_primary) || product.image_url ? 1 : 0);
  const videoCount =
    numberValue(content.video_count) ?? arrayCount(media.videos);
  const relationshipCount = Object.values(relationships).reduce<number>(
    (total, value) => total + arrayCount(value),
    0,
  );
  const description =
    displayValue(product.description) ??
    displayValue(product.description_short) ??
    displayValue(product.description_full);
  const role = displayValue(product.role)?.toLowerCase() ?? "";
  return {
    enriched:
      role.includes("pdp-enriched") ||
      sourceFields.length > 0 ||
      Boolean(description || product.specification || product.identifiers),
    description,
    seller: displayValue(product.seller),
    category: displayValue(product.category_path),
    condition: displayValue(product.item_condition),
    rating: numberValue(reviews.rating),
    reviewCount: numberValue(reviews.reviews_count ?? reviews.rating_count),
    demand:
      monthlySales !== null
        ? `${monthlySales.toLocaleString()} monthly sales`
        : weeklySales !== null
          ? `${weeklySales.toLocaleString()} weekly sales`
          : null,
    fulfillment: fulfillmentLabels,
    imageCount,
    videoCount,
    relationshipCount,
    sourceFieldCount: sourceFields.length,
    unmappedFields,
  };
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
    ["Fulfillment", product.fulfillment],
    ["Reviews", product.reviews],
    ["Demand context", product.demand],
  ] as const;
  const seller = displayValue(product.seller);
  if (seller) rows.push({ section: "Product", label: "Seller", value: seller });
  const category = displayValue(product.category_path);
  if (category)
    rows.push({ section: "Product", label: "Category", value: category });
  const condition = displayValue(product.item_condition);
  if (condition)
    rows.push({ section: "Product", label: "Condition", value: condition });
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

function comparisonKey(row: ProductDetailRow) {
  return `${row.section}\u0000${row.label}`;
}

function normalizedComparisonValue(value: string) {
  return value.trim().toLocaleLowerCase().replaceAll(/\s+/g, " ");
}

export function compareProductDetails(
  product: MatchReviewProduct,
  counterpart: MatchReviewProduct,
): ProductComparisonRow[] {
  const counterpartRows = new Map(
    productDetailRows(counterpart).map((row) => [comparisonKey(row), row]),
  );
  const productRows = productDetailRows(product);
  const seen = new Set(productRows.map(comparisonKey));
  const rows: ProductComparisonRow[] = productRows.map((row) => {
    const counterpartRow = counterpartRows.get(comparisonKey(row));
    const counterpartValue = counterpartRow?.value ?? null;
    return {
      ...row,
      counterpartValue,
      status:
        counterpartValue === null
          ? "missing"
          : normalizedComparisonValue(counterpartValue) ===
              normalizedComparisonValue(row.value)
            ? "aligned"
            : "different",
    };
  });
  for (const counterpartRow of counterpartRows.values()) {
    if (seen.has(comparisonKey(counterpartRow))) continue;
    rows.push({
      ...counterpartRow,
      value: "Not supplied",
      counterpartValue: counterpartRow.value,
      status: "missing",
    });
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

const statusPriority: Record<MatchReviewConnection["status"], number> = {
  ambiguous: 0,
  suggested: 1,
  confirmed: 2,
  rejected: 3,
};

function strongestEvidence(connection: MatchReviewConnection) {
  return connection.profile_evidence.reduce(
    (best, evidence) => ({
      geographies: Math.max(best.geographies, evidence.geographies ?? 0),
      matches: Math.max(best.matches, evidence.matches ?? 0),
      gap: Math.max(best.gap, Math.abs(evidence.median_gap ?? 0)),
    }),
    { geographies: 0, matches: 0, gap: 0 },
  );
}

export function rankMatchReviewConnections(
  connections: MatchReviewConnection[],
) {
  return [...connections].sort((left, right) => {
    const leftEvidence = strongestEvidence(left);
    const rightEvidence = strongestEvidence(right);
    return (
      statusPriority[left.status] - statusPriority[right.status] ||
      rightEvidence.geographies - leftEvidence.geographies ||
      rightEvidence.matches - leftEvidence.matches ||
      rightEvidence.gap - leftEvidence.gap ||
      left.benchmark_product_id.localeCompare(right.benchmark_product_id) ||
      left.competitor_product_id.localeCompare(right.competitor_product_id)
    );
  });
}
