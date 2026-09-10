import type { RetailCompetitiveIntelligenceCanonicalReportDataset } from "@rci/contracts";

type CanonicalDataset = RetailCompetitiveIntelligenceCanonicalReportDataset;

export type CanonicalChecklistStatus = "passed" | "warning" | "blocked";

export interface CanonicalChecklistItem {
  id: string;
  label: string;
  status: CanonicalChecklistStatus;
  detail: string;
}

export interface CanonicalIntegrityIssue {
  code: string;
  message: string;
  relationshipId?: string;
}

function governanceStatus(
  status: "passed" | "passed_with_unverified_competitors" | "blocked",
): CanonicalChecklistStatus {
  if (status === "blocked") return "blocked";
  if (status === "passed_with_unverified_competitors") return "warning";
  return "passed";
}

function readinessStatus(
  status: CanonicalDataset["readiness"]["status"],
): CanonicalChecklistStatus {
  if (status === "blocked") return "blocked";
  if (status === "ready_with_caveats") return "warning";
  return "passed";
}

function normalizationStatus(
  status: CanonicalDataset["price_normalization"]["status"],
): CanonicalChecklistStatus {
  if (status === "blocked") return "blocked";
  if (status === "passed_with_exclusions") return "warning";
  return "passed";
}

function coverageStatus(
  status: CanonicalDataset["qa"]["retailer_coverage_status"],
): CanonicalChecklistStatus {
  if (status === "blocked") return "blocked";
  if (status === "passed_with_exclusions") return "warning";
  return "passed";
}

function statusReasonDetail(
  reason: CanonicalDataset["readiness"]["blocking_reasons"][number] | undefined,
) {
  if (!reason) return null;
  return reason.next_action
    ? `${reason.message} Next action: ${reason.next_action}`
    : reason.message;
}

export function canonicalReportChecklist(
  dataset: CanonicalDataset,
): CanonicalChecklistItem[] {
  return [
    {
      id: "readiness",
      label: "Report readiness",
      status: readinessStatus(dataset.readiness.status),
      detail:
        statusReasonDetail(dataset.readiness.blocking_reasons[0]) ??
        statusReasonDetail(dataset.readiness.warnings[0]) ??
        "Canonical report inputs are ready for preview review.",
    },
    {
      id: "seller-governance",
      label: "Seller governance",
      status: governanceStatus(dataset.seller_governance.status),
      detail: dataset.seller_governance.excluded_product_count
        ? `${dataset.seller_governance.excluded_product_count.toLocaleString()} benchmark products excluded because seller qualification failed.`
        : "Benchmark products are seller-qualified or explicitly not applicable.",
    },
    {
      id: "price-normalization",
      label: "Price normalization",
      status: normalizationStatus(dataset.price_normalization.status),
      detail: dataset.price_normalization.invalid_price_record_count
        ? `${dataset.price_normalization.invalid_price_record_count.toLocaleString()} relationships excluded for missing or nonpositive reportable prices.`
        : "All included relationships use positive reportable prices; zero sentinels are not rendered as prices.",
    },
    {
      id: "distribution-evidence",
      label: "Distribution evidence",
      status: coverageStatus(dataset.qa.retailer_coverage_status),
      detail: dataset.qa.products_without_valid_distribution_count
        ? `${dataset.qa.products_without_valid_distribution_count.toLocaleString()} relationships excluded for missing governed distribution evidence.`
        : "Included relationships have governed positive-price Search distribution evidence.",
    },
    {
      id: "match-certification",
      label: "Match certification",
      status: dataset.qa.match_certification_complete ? "passed" : "warning",
      detail: dataset.qa.match_certification_complete
        ? "No pending match-certification work is surfaced in this canonical dataset."
        : "Some match-certification work may still be pending; review before buyer-facing export.",
    },
    {
      id: "product-images",
      label: "Product images",
      status: dataset.qa.products_without_image_count ? "warning" : "passed",
      detail: dataset.qa.products_without_image_count
        ? `${dataset.qa.products_without_image_count.toLocaleString()} included product tiles are missing images.`
        : "Every included product tile has an image URL.",
    },
  ];
}

export function canonicalReportIntegrityIssues(
  dataset: CanonicalDataset,
): CanonicalIntegrityIssue[] {
  const issues: CanonicalIntegrityIssue[] = [];
  const relationships = dataset.product_relationships;
  const excludedRelationships = dataset.excluded_relationships;
  const relationshipIds = new Set<string>();
  const outcomeCounts = relationships.reduce(
    (counts, relationship) => {
      const outcome = relationship.comparison.outcome;
      counts[outcome] += 1;
      return counts;
    },
    {
      walmart_wins: 0,
      competitor_wins: 0,
      parity: 0,
      unscored: 0,
    },
  );

  if (dataset.summary.relationship_count !== relationships.length) {
    issues.push({
      code: "summary_relationship_count_mismatch",
      message:
        "Summary relationship count does not match included product relationships.",
    });
  }
  if (
    dataset.summary.excluded_relationship_count !== excludedRelationships.length
  ) {
    issues.push({
      code: "summary_excluded_relationship_count_mismatch",
      message:
        "Summary excluded relationship count does not match excluded relationships.",
    });
  }
  if (dataset.qa.included_relationship_count !== relationships.length) {
    issues.push({
      code: "qa_included_relationship_count_mismatch",
      message:
        "QA included relationship count does not match included product relationships.",
    });
  }
  if (dataset.qa.excluded_relationship_count !== excludedRelationships.length) {
    issues.push({
      code: "qa_excluded_relationship_count_mismatch",
      message:
        "QA excluded relationship count does not match excluded relationships.",
    });
  }
  if (dataset.summary.walmart_win_count !== outcomeCounts.walmart_wins) {
    issues.push({
      code: "walmart_win_count_mismatch",
      message: "Walmart win count does not reconcile to relationship outcomes.",
    });
  }
  if (dataset.summary.competitor_win_count !== outcomeCounts.competitor_wins) {
    issues.push({
      code: "competitor_win_count_mismatch",
      message:
        "Competitor win count does not reconcile to relationship outcomes.",
    });
  }
  if (dataset.summary.parity_count !== outcomeCounts.parity) {
    issues.push({
      code: "parity_count_mismatch",
      message: "Parity count does not reconcile to relationship outcomes.",
    });
  }
  if (dataset.summary.unscored_count !== outcomeCounts.unscored) {
    issues.push({
      code: "unscored_count_mismatch",
      message: "Unscored count does not reconcile to relationship outcomes.",
    });
  }

  const distribution = dataset.contracts.distribution;
  if (
    distribution.basis !== "positive_price_store_search_result" ||
    distribution.price_rule !== "price_gt_zero" ||
    distribution.inventory_claim ||
    distribution.stock_status_used ||
    distribution.sponsorship_used ||
    distribution.extrapolation
  ) {
    issues.push({
      code: "invalid_distribution_contract",
      message:
        "Distribution contract must use positive-price store Search presence without inventory, stock, sponsorship, or extrapolation.",
    });
  }
  if (dataset.contracts.service_area_presence.presented_as_store_count) {
    issues.push({
      code: "service_area_presented_as_store_count",
      message: "Service-area presence cannot be presented as physical stores.",
    });
  }

  for (const relationship of relationships) {
    const relationshipId = relationship.relationship_id;
    if (relationshipIds.has(relationshipId)) {
      issues.push({
        code: "duplicate_relationship_id",
        message: "Relationship IDs must be unique.",
        relationshipId,
      });
    }
    relationshipIds.add(relationshipId);

    const benchmarkPrice = relationship.benchmark_product.price.reporting_price;
    const competitorPrice =
      relationship.competitor_product.price.reporting_price;
    if (benchmarkPrice <= 0 || competitorPrice <= 0) {
      issues.push({
        code: "nonpositive_reporting_price",
        message: "Included relationships must have positive reportable prices.",
        relationshipId,
      });
    }
    if (
      Math.abs(
        relationship.comparison.price_delta -
          (benchmarkPrice - competitorPrice),
      ) > 0.000_1
    ) {
      issues.push({
        code: "price_delta_mismatch",
        message:
          "Price delta does not reconcile to displayed reporting prices.",
        relationshipId,
      });
    }
    if (
      relationship.comparison.outcome === "walmart_wins" &&
      relationship.comparison.price_delta > 0
    ) {
      issues.push({
        code: "walmart_win_positive_delta",
        message:
          "Outcome says Walmart wins but displayed price delta says Walmart is higher.",
        relationshipId,
      });
    }
    if (
      relationship.comparison.outcome === "competitor_wins" &&
      relationship.comparison.price_delta < 0
    ) {
      issues.push({
        code: "competitor_win_negative_delta",
        message:
          "Outcome says competitor wins but displayed price delta says Walmart is lower.",
        relationshipId,
      });
    }
    if (
      relationship.benchmark_product.seller_status !== "qualified" &&
      relationship.benchmark_product.seller_status !== "not_applicable"
    ) {
      issues.push({
        code: "benchmark_seller_not_qualified",
        message:
          "Included benchmark products must be seller-qualified or explicitly not applicable.",
        relationshipId,
      });
    }
    if (
      relationship.benchmark_product.distribution
        .physical_store_distribution_count < 0 ||
      relationship.competitor_product.distribution
        .physical_store_distribution_count < 0
    ) {
      issues.push({
        code: "negative_distribution_count",
        message: "Distribution counts cannot be negative.",
        relationshipId,
      });
    }
  }

  return issues;
}
