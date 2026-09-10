import type { RetailCompetitiveIntelligenceCanonicalReportDataset } from "@rci/contracts";

import type {
  AnalysisRecord,
  AnalysisReportView,
  AssortmentProduct,
  ProductDecision,
  ProductMatchCandidate,
  RetailerScorecard,
} from "./api";

type CanonicalDataset = RetailCompetitiveIntelligenceCanonicalReportDataset;
type CanonicalProduct =
  CanonicalDataset["product_relationships"][number]["benchmark_product"];
type CanonicalCompetitorProduct =
  CanonicalDataset["product_relationships"][number]["competitor_product"];
type CanonicalOutcome =
  CanonicalDataset["product_relationships"][number]["comparison"]["outcome"];
type ExcludedRelationship = CanonicalDataset["excluded_relationships"][number];
type ReportableProductDecision = ProductDecision | ProductMatchCandidate;

const DISTRIBUTION_CONTRACT: CanonicalDataset["contracts"]["distribution"] = {
  version: "1.0.0",
  basis: "positive_price_store_search_result",
  grain: "retailer_product_id_x_store_id",
  deduplication: "distinct_store_id_per_product",
  price_rule: "price_gt_zero",
  inventory_claim: false,
  stock_status_used: false,
  sponsorship_used: false,
  extrapolation: false,
};

const SERVICE_AREA_PRESENCE_CONTRACT: CanonicalDataset["contracts"]["service_area_presence"] =
  {
    version: "1.0.0",
    basis: "positive_price_service_area_search_result",
    grain: "retailer_product_id_x_service_area",
    price_rule: "price_gt_zero",
    presented_as_store_count: false,
  };

function identityToken(value: unknown) {
  return String(value ?? "")
    .toLocaleLowerCase("en-US")
    .replace(/\(us\)/g, "")
    .replace(/[^a-z0-9]/g, "");
}

function relationshipKey(row: {
  competitor: string;
  benchmark_product_id: string;
  competitor_product_id: string;
  profile_id?: string | null;
}) {
  return [
    identityToken(row.competitor),
    row.benchmark_product_id,
    row.competitor_product_id,
    row.profile_id ?? "",
  ].join("::");
}

function finitePositive(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? value
    : null;
}

function finiteNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function recordValue(row: unknown, key: string) {
  if (!row || typeof row !== "object") return undefined;
  return (row as Record<string, unknown>)[key];
}

function textValue(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function maybeUrl(value: unknown) {
  return textValue(value);
}

function assortmentIndex(reportView: AnalysisReportView) {
  const entries = (reportView.assortment_analysis?.retailers ?? []).flatMap(
    (retailer) =>
      (retailer.products ?? []).map(
        (product) =>
          [
            `${identityToken(retailer.retailer)}::${product.product_id}`,
            product,
          ] as const,
      ),
  );
  return new Map(entries);
}

function productFromAssortment(
  products: Map<string, AssortmentProduct>,
  retailerIdOrName: string,
  productId: string,
) {
  return (
    products.get(`${identityToken(retailerIdOrName)}::${productId}`) ?? null
  );
}

function scorecardIndex(reportView: AnalysisReportView) {
  const entries = reportView.retailer_scorecards.map(
    (scorecard) =>
      [
        `${identityToken(scorecard.competitor_id)}::${scorecard.profile_id}`,
        scorecard,
      ] as const,
  );
  return new Map(entries);
}

function scorecardForDecision(
  scorecards: Map<string, RetailerScorecard>,
  decision: ReportableProductDecision,
) {
  return (
    scorecards.get(
      `${identityToken(decision.competitor)}::${decision.profile_id ?? ""}`,
    ) ?? null
  );
}

function candidateIndex(reportView: AnalysisReportView) {
  const byRelationshipId = new Map<string, ProductMatchCandidate>();
  const byPair = new Map<string, ProductMatchCandidate>();
  for (const candidate of reportView.match_candidates ?? []) {
    if (candidate.relationship_id) {
      byRelationshipId.set(String(candidate.relationship_id), candidate);
    }
    byPair.set(relationshipKey(candidate), candidate);
  }
  return { byRelationshipId, byPair };
}

function candidateForDecision(
  candidates: ReturnType<typeof candidateIndex>,
  decision: ReportableProductDecision,
) {
  if (decision.relationship_id) {
    const byId = candidates.byRelationshipId.get(
      String(decision.relationship_id),
    );
    if (byId) return byId;
  }
  return candidates.byPair.get(relationshipKey(decision)) ?? null;
}

function sellerStatus(
  product: AssortmentProduct | null,
  row: ProductDecision | ProductMatchCandidate,
  retailerId: string,
):
  | CanonicalProduct["seller_status"]
  | CanonicalCompetitorProduct["seller_status"]
  | null {
  const explicit = textValue(recordValue(row, "seller_status"));
  if (
    explicit === "qualified" ||
    explicit === "not_qualified" ||
    explicit === "unverified" ||
    explicit === "not_applicable"
  ) {
    return explicit;
  }
  const seller =
    textValue(recordValue(row, "seller")) ?? product?.seller ?? null;
  if (identityToken(retailerId) === "walmartus") {
    if (seller && seller.toLocaleLowerCase("en-US") === "walmart.com") {
      return "qualified";
    }
    return null;
  }
  return "not_applicable";
}

function benchmarkSellerStatus(
  product: AssortmentProduct | null,
  row: ProductDecision | ProductMatchCandidate,
  retailerId: string,
): CanonicalProduct["seller_status"] | null {
  const status = sellerStatus(product, row, retailerId);
  return status === "qualified" || status === "not_applicable" ? status : null;
}

function distribution(product: AssortmentProduct | null) {
  if (!product) return null;
  const physical = finiteNumber(product.distribution_store_count);
  const serviceArea = finiteNumber(product.service_area_presence_count);
  if (physical === null || serviceArea === null) return null;
  return {
    physical_store_distribution_count: physical,
    service_area_presence_count: serviceArea,
    searched_store_count: null,
  };
}

function reportingPriceLabel(price: number, unitBasis: string) {
  return `$${price.toFixed(2)}${unitBasis ? `/${unitBasis}` : ""}`;
}

function canonicalPrice(
  price: unknown,
  unitBasis: string,
  comparisonMetric?: string | null,
): CanonicalProduct["price"] | null {
  const reportingPrice = finitePositive(price);
  if (reportingPrice === null) return null;
  const packagePrice =
    comparisonMetric === "package_price" || unitBasis === "package"
      ? reportingPrice
      : null;
  return {
    reporting_price: reportingPrice,
    reporting_price_label: reportingPriceLabel(reportingPrice, unitBasis),
    package_price: packagePrice,
    normalized_unit_price: packagePrice === null ? reportingPrice : null,
    regular_price: null,
    discounted_price: null,
    currency: "USD",
  };
}

function packageSummary(
  unitBasis: string,
  scorecard: RetailerScorecard | null,
) {
  return {
    label: scorecard?.package_basis ?? "reported comparison basis",
    unit_basis: unitBasis,
    quantity: null,
    unit: null,
  };
}

function evidenceObservedAt(
  analysis: AnalysisRecord,
  reportView: AnalysisReportView,
) {
  const source = recordValue(analysis.result, "source");
  return (
    textValue(recordValue(source, "observed_end")) ??
    textValue(recordValue(analysis.result, "generated_at")) ??
    reportView.generated_at
  );
}

function outcomeFromDisplayedPriceDelta(priceDelta: number): CanonicalOutcome {
  if (Math.abs(priceDelta) < 0.000_001) return "parity";
  return priceDelta < 0 ? "walmart_wins" : "competitor_wins";
}

function excluded(
  decision: ReportableProductDecision,
  reasonCode: string,
  reason: string,
): ExcludedRelationship {
  return {
    relationship_id:
      decision.relationship_id ??
      decision.id ??
      `${decision.benchmark_product_id}:${decision.competitor}:${decision.competitor_product_id}`,
    benchmark_product_id: decision.benchmark_product_id,
    competitor_product_id: decision.competitor_product_id,
    competitor_retailer_id: decision.competitor,
    reason_code: reasonCode,
    reason,
    evidence_refs: decision.relationship_id
      ? [{ kind: "match_decision", id: String(decision.relationship_id) }]
      : [],
  };
}

function canonicalRelationship(
  analysis: AnalysisRecord,
  reportView: AnalysisReportView,
  products: Map<string, AssortmentProduct>,
  scorecards: Map<string, RetailerScorecard>,
  candidates: ReturnType<typeof candidateIndex>,
  decision: ReportableProductDecision,
): {
  relationship: CanonicalDataset["product_relationships"][number] | null;
  excluded?: ExcludedRelationship;
} {
  if ((decision.qa_status ?? "ready") !== "ready") {
    return {
      relationship: null,
      excluded: excluded(
        decision,
        "decision_not_ready",
        "Relationship decision is not ready for buyer-facing reporting.",
      ),
    };
  }
  if ((decision.matches ?? 0) <= 0) {
    return {
      relationship: null,
      excluded: excluded(
        decision,
        "no_positive_price_comparison",
        "Relationship has no matched positive-price comparison observations.",
      ),
    };
  }
  const candidate = candidateForDecision(candidates, decision);
  const scorecard = scorecardForDecision(scorecards, decision);
  const benchmarkRetailerId = reportView.retailer_scope.benchmark.id;
  const competitorRetailer =
    reportView.retailer_scope.competitors.find(
      (retailer) =>
        identityToken(retailer.id) === identityToken(decision.competitor) ||
        identityToken(retailer.name) === identityToken(decision.competitor),
    ) ?? null;
  const competitorRetailerId = competitorRetailer?.id ?? decision.competitor;
  const benchmarkAssortment = productFromAssortment(
    products,
    benchmarkRetailerId,
    decision.benchmark_product_id,
  );
  const competitorAssortment = productFromAssortment(
    products,
    competitorRetailerId,
    decision.competitor_product_id,
  );
  const benchmarkSeller = benchmarkSellerStatus(
    benchmarkAssortment,
    candidate ?? decision,
    benchmarkRetailerId,
  );
  if (benchmarkSeller !== "qualified" && benchmarkSeller !== "not_applicable") {
    return {
      relationship: null,
      excluded: excluded(
        decision,
        "benchmark_seller_not_qualified",
        "Benchmark product is not seller-qualified for buyer-facing reporting.",
      ),
    };
  }
  const benchmarkDistribution = distribution(benchmarkAssortment);
  if (!benchmarkDistribution) {
    return {
      relationship: null,
      excluded: excluded(
        decision,
        "missing_benchmark_distribution",
        "Benchmark product lacks governed positive-price store Search distribution evidence.",
      ),
    };
  }
  const competitorDistribution = distribution(competitorAssortment);
  if (!competitorDistribution) {
    return {
      relationship: null,
      excluded: excluded(
        decision,
        "missing_competitor_distribution",
        "Competitor product lacks governed positive-price Search distribution evidence.",
      ),
    };
  }
  const comparisonMetric =
    decision.comparison_metric ?? scorecard?.comparison_metric ?? null;
  const unitBasis = String(
    scorecard?.price_unit ?? comparisonMetric ?? "reported unit",
  ).replace(/^USD\//, "");
  const benchmarkPrice = canonicalPrice(
    decision.median_benchmark_price,
    unitBasis,
    comparisonMetric,
  );
  const competitorPrice = canonicalPrice(
    decision.median_competitor_price,
    unitBasis,
    comparisonMetric,
  );
  if (!benchmarkPrice || !competitorPrice) {
    return {
      relationship: null,
      excluded: excluded(
        decision,
        "invalid_or_missing_price",
        "Relationship lacks positive reportable benchmark and competitor prices.",
      ),
    };
  }
  const priceDelta =
    benchmarkPrice.reporting_price - competitorPrice.reporting_price;
  const priceDeltaPercent = priceDelta / competitorPrice.reporting_price;
  const relationshipId =
    decision.relationship_id ??
    candidate?.relationship_id ??
    `${analysis.analysis_id}:${decision.benchmark_product_id}:${competitorRetailerId}:${decision.competitor_product_id}`;
  return {
    relationship: {
      relationship_id: String(relationshipId),
      benchmark_product: {
        retailer_id: benchmarkRetailerId,
        retailer_product_id: decision.benchmark_product_id,
        title:
          decision.benchmark_product_name ||
          candidate?.benchmark_product_name ||
          benchmarkAssortment?.name ||
          decision.benchmark_product_id,
        url:
          maybeUrl(decision.benchmark_product_url) ??
          maybeUrl(candidate?.benchmark_product_url) ??
          benchmarkAssortment?.url ??
          null,
        image_url:
          maybeUrl(decision.benchmark_image_url) ??
          maybeUrl(candidate?.benchmark_image_url) ??
          benchmarkAssortment?.image_url ??
          null,
        brand:
          benchmarkAssortment?.observed_brand ??
          benchmarkAssortment?.brand ??
          null,
        brand_type: benchmarkAssortment?.brand_type ?? "unclassified",
        seller_status: benchmarkSeller,
        package: packageSummary(unitBasis, scorecard),
        price: benchmarkPrice,
        distribution: benchmarkDistribution,
      },
      competitor_product: {
        retailer_id: competitorRetailerId,
        retailer_product_id: decision.competitor_product_id,
        title:
          decision.competitor_product_name ||
          candidate?.competitor_product_name ||
          competitorAssortment?.name ||
          decision.competitor_product_id,
        url:
          maybeUrl(decision.competitor_product_url) ??
          maybeUrl(candidate?.competitor_product_url) ??
          competitorAssortment?.url ??
          null,
        image_url:
          maybeUrl(decision.competitor_image_url) ??
          maybeUrl(candidate?.competitor_image_url) ??
          competitorAssortment?.image_url ??
          null,
        brand:
          competitorAssortment?.observed_brand ??
          competitorAssortment?.brand ??
          null,
        brand_type: competitorAssortment?.brand_type ?? "unclassified",
        seller_status:
          sellerStatus(
            competitorAssortment,
            candidate ?? decision,
            competitorRetailerId,
          ) ?? "not_applicable",
        package: packageSummary(unitBasis, scorecard),
        price: competitorPrice,
        distribution: competitorDistribution,
      },
      comparison: {
        comparison_basis:
          decision.profile_id ?? scorecard?.profile_id ?? "unspecified",
        unit_basis: unitBasis,
        price_delta: priceDelta,
        price_delta_percent: priceDeltaPercent,
        outcome: outcomeFromDisplayedPriceDelta(priceDelta),
        match_certification: {
          status:
            decision.relationship_status === "rejected"
              ? "certified_not_comparable"
              : "certified_comparable",
          source: reportView.certification_coverage
            ? "matching_v2_gold_set"
            : "legacy_governed",
        },
      },
      evidence_refs: [
        { kind: "match_decision", id: decision.relationship_id ?? decision.id },
      ],
    },
  };
}

function profileRank(reportView: AnalysisReportView) {
  return new Map(
    reportView.comparison_bases.map((basis, index) => [
      basis.profile_id,
      basis.scorecard_role === "preferred" ? -1 : index,
    ]),
  );
}

function reportableCandidateFallback(
  reportView: AnalysisReportView,
): ProductMatchCandidate[] {
  if ((reportView.product_decisions ?? []).length > 0) {
    return [];
  }
  // Some governed matching-v2 publications carry product-level decision evidence
  // only in match_candidates. Treat those rows as reportable only after the same
  // relationship, QA, positive-price, seller, and distribution guardrails are
  // applied below; do not use unmatched or zero-price candidate rows.
  const ranks = profileRank(reportView);
  const admitted = (reportView.match_candidates ?? []).filter(
    (candidate) =>
      (candidate.relationship_status === "suggested" ||
        candidate.relationship_status === "confirmed") &&
      (candidate.qa_status ?? "ready") === "ready" &&
      (candidate.matches ?? 0) > 0 &&
      finitePositive(candidate.median_benchmark_price) !== null &&
      finitePositive(candidate.median_competitor_price) !== null,
  );
  const selected = new Map<string, ProductMatchCandidate>();
  for (const candidate of admitted) {
    const relationshipId = textValue(candidate.relationship_id);
    const key =
      relationshipId ??
      [
        identityToken(candidate.competitor),
        candidate.benchmark_product_id,
        candidate.competitor_product_id,
      ].join("::");
    const current = selected.get(key);
    if (!current) {
      selected.set(key, candidate);
      continue;
    }
    const candidateRank = ranks.get(candidate.profile_id ?? "") ?? 9999;
    const currentRank = ranks.get(current.profile_id ?? "") ?? 9999;
    if (
      candidateRank < currentRank ||
      (candidateRank === currentRank &&
        (candidate.matches ?? 0) > (current.matches ?? 0))
    ) {
      selected.set(key, candidate);
    }
  }
  return [...selected.values()].sort(
    (left, right) =>
      (ranks.get(left.profile_id ?? "") ?? 9999) -
        (ranks.get(right.profile_id ?? "") ?? 9999) ||
      identityToken(left.competitor).localeCompare(
        identityToken(right.competitor),
      ) ||
      left.benchmark_product_name.localeCompare(right.benchmark_product_name) ||
      String(
        left.competitor_product_name ?? left.competitor_product_id,
      ).localeCompare(
        String(right.competitor_product_name ?? right.competitor_product_id),
      ),
  );
}

export function canonicalReportDatasetFromReportView(
  analysis: AnalysisRecord,
  reportView: AnalysisReportView,
): CanonicalDataset {
  const products = assortmentIndex(reportView);
  const scorecards = scorecardIndex(reportView);
  const candidates = candidateIndex(reportView);
  const relationships: CanonicalDataset["product_relationships"] = [];
  const excludedRelationships: ExcludedRelationship[] = [];
  const sourceRows =
    (reportView.product_decisions ?? []).length > 0
      ? (reportView.product_decisions ?? [])
      : reportableCandidateFallback(reportView);
  for (const decision of sourceRows) {
    const projected = canonicalRelationship(
      analysis,
      reportView,
      products,
      scorecards,
      candidates,
      decision,
    );
    if (projected.relationship) relationships.push(projected.relationship);
    if (projected.excluded) excludedRelationships.push(projected.excluded);
  }
  const summary = relationships.reduce<CanonicalDataset["summary"]>(
    (counts: CanonicalDataset["summary"], relationship) => {
      const current = relationship.comparison.outcome;
      if (current === "walmart_wins") counts.walmart_win_count += 1;
      else if (current === "competitor_wins") counts.competitor_win_count += 1;
      else if (current === "parity") counts.parity_count += 1;
      else counts.unscored_count += 1;
      return counts;
    },
    {
      relationship_count: relationships.length,
      walmart_win_count: 0,
      competitor_win_count: 0,
      parity_count: 0,
      unscored_count: 0,
      excluded_relationship_count: excludedRelationships.length,
    },
  );
  const invalidPriceRecordCount = excludedRelationships.filter(
    (row) => row.reason_code === "invalid_or_missing_price",
  ).length;
  const unverifiedSellerProductCount = excludedRelationships.filter(
    (row) => row.reason_code === "benchmark_seller_not_qualified",
  ).length;
  const productsWithoutImageCount = relationships.reduce<number>(
    (count: number, relationship) =>
      count +
      (relationship.benchmark_product.image_url ? 0 : 1) +
      (relationship.competitor_product.image_url ? 0 : 1),
    0,
  );
  const productsWithoutValidDistributionCount = excludedRelationships.filter(
    (row) =>
      row.reason_code === "missing_benchmark_distribution" ||
      row.reason_code === "missing_competitor_distribution",
  ).length;
  const readinessBlockingReasons: CanonicalDataset["readiness"]["blocking_reasons"] =
    (reportView.report_readiness.blocking_reasons ?? []).map((reason) => ({
      code: String(reason.code ?? "report_not_ready"),
      message: String(reason.message ?? "Report is not ready."),
      next_action: null,
    }));
  if (
    relationships.length === 0 &&
    !readinessBlockingReasons.some(
      (reason) => reason.code === "no_reportable_product_relationships",
    )
  ) {
    readinessBlockingReasons.push({
      code: "no_reportable_product_relationships",
      message:
        "No reportable product relationships passed the canonical guardrails, so the buyer-facing report is not ready.",
      next_action: excludedRelationships.length
        ? "Review the Evidence & QA exclusions, repair missing seller, price, or distribution evidence, then rebuild the report dataset from retained evidence."
        : "Confirm Product Pack coverage and match certification produced product decisions with positive prices and governed distribution evidence, then rebuild the report dataset from retained evidence.",
    });
  }
  const readinessWarnings: CanonicalDataset["readiness"]["warnings"] = (
    reportView.report_readiness.warnings ?? []
  ).map((warning) => ({
    code: String(warning.code ?? "report_warning"),
    message: String(warning.message ?? "Report warning."),
    next_action: null,
  }));
  const readinessStatus: CanonicalDataset["readiness"]["status"] =
    readinessBlockingReasons.length > 0
      ? "blocked"
      : reportView.report_readiness.status === "ready"
        ? "ready"
        : "ready_with_caveats";

  return {
    schema_version: "1.0.0",
    report_id: `${analysis.analysis_id}:canonical-report-dataset`,
    analysis_id: analysis.analysis_id,
    generated_at: reportView.generated_at,
    evidence_observed_at: evidenceObservedAt(analysis, reportView),
    benchmark_retailer: reportView.retailer_scope.benchmark,
    competitors: reportView.retailer_scope.competitors,
    product_pack: {
      id: reportView.product_pack.id,
      name: reportView.product_pack.name,
      version: reportView.product_pack.version,
      checksum: null,
    },
    retailer_packs: [],
    contracts: {
      distribution: DISTRIBUTION_CONTRACT,
      service_area_presence: SERVICE_AREA_PRESENCE_CONTRACT,
    },
    readiness: {
      status: readinessStatus,
      blocking_reasons: readinessBlockingReasons,
      warnings: readinessWarnings,
    },
    seller_governance: {
      status: unverifiedSellerProductCount ? "blocked" : "passed",
      benchmark_requirement: "qualified_seller_or_not_applicable",
      unverified_product_count: unverifiedSellerProductCount,
      excluded_product_count: unverifiedSellerProductCount,
    },
    price_normalization: {
      status: invalidPriceRecordCount ? "passed_with_exclusions" : "passed",
      unit_basis: relationships[0]?.comparison.unit_basis ?? "reported unit",
      zero_price_sentinel_rule: "zero_regular_or_discounted_price_is_missing",
      invalid_price_record_count: invalidPriceRecordCount,
    },
    summary,
    product_relationships: relationships,
    excluded_relationships: excludedRelationships,
    qa: {
      included_relationship_count: relationships.length,
      excluded_relationship_count: excludedRelationships.length,
      invalid_price_record_count: invalidPriceRecordCount,
      unverified_seller_product_count: unverifiedSellerProductCount,
      products_without_image_count: productsWithoutImageCount,
      products_without_valid_distribution_count:
        productsWithoutValidDistributionCount,
      match_certification_complete:
        reportView.certification_coverage?.pending_unreviewed_count === 0 ||
        reportView.match_governance.ambiguous === 0,
      product_pack_coverage_status: relationships.length ? "passed" : "blocked",
      retailer_coverage_status: relationships.length
        ? excludedRelationships.length
          ? "passed_with_exclusions"
          : "passed"
        : "blocked",
    },
  };
}
