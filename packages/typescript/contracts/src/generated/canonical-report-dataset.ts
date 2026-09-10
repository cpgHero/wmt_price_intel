/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceCanonicalReportDataset {
  schema_version: "1.0.0";
  report_id: string;
  analysis_id: string;
  generated_at: string;
  evidence_observed_at: string;
  benchmark_retailer: IdName;
  competitors: IdName[];
  product_pack: ProductPack;
  retailer_packs: RetailerPack[];
  contracts: Contracts;
  readiness: Readiness;
  seller_governance: SellerGovernance;
  price_normalization: PriceNormalization;
  summary: Summary;
  product_relationships: ProductRelationship[];
  excluded_relationships: ExcludedRelationship[];
  qa: Qa;
}
export interface IdName {
  id: string;
  name: string;
}
export interface ProductPack {
  id: string;
  name: string;
  version: string;
  checksum?: string | null;
}
export interface RetailerPack {
  retailer_id: string;
  version: string;
  checksum: string;
}
export interface Contracts {
  distribution: DistributionContract;
  service_area_presence: ServiceAreaPresenceContract;
}
export interface DistributionContract {
  version: "1.0.0";
  basis: "positive_price_store_search_result";
  grain: "retailer_product_id_x_store_id";
  deduplication: "distinct_store_id_per_product";
  price_rule: "price_gt_zero";
  inventory_claim: false;
  stock_status_used: false;
  sponsorship_used: false;
  extrapolation: false;
}
export interface ServiceAreaPresenceContract {
  version: "1.0.0";
  basis: "positive_price_service_area_search_result";
  grain: "retailer_product_id_x_service_area";
  price_rule: "price_gt_zero";
  presented_as_store_count: false;
}
export interface Readiness {
  status: "ready" | "ready_with_caveats" | "blocked";
  blocking_reasons: StatusReason[];
  warnings: StatusReason[];
}
export interface StatusReason {
  code: string;
  message: string;
  next_action?: string | null;
}
export interface SellerGovernance {
  status: "passed" | "passed_with_unverified_competitors" | "blocked";
  benchmark_requirement: "qualified_seller_or_not_applicable";
  unverified_product_count: number;
  excluded_product_count: number;
}
export interface PriceNormalization {
  status: "passed" | "passed_with_exclusions" | "blocked";
  unit_basis: string;
  zero_price_sentinel_rule: "zero_regular_or_discounted_price_is_missing";
  invalid_price_record_count: number;
}
export interface Summary {
  relationship_count: number;
  walmart_win_count: number;
  competitor_win_count: number;
  parity_count: number;
  unscored_count: number;
  excluded_relationship_count: number;
}
export interface ProductRelationship {
  relationship_id: string;
  benchmark_product: BenchmarkProduct;
  competitor_product: Product;
  comparison: Comparison;
  evidence_refs: EvidenceRef[];
}
export interface BenchmarkProduct {
  retailer_id: string;
  retailer_product_id: string;
  title: string;
  url: string | null;
  image_url: string | null;
  brand: string | null;
  brand_type: "private_label" | "regional" | "national" | "unclassified";
  seller_status: "qualified" | "not_applicable";
  package: Package;
  price: Price;
  distribution: Distribution;
}
export interface Package {
  label: string;
  unit_basis: string;
  quantity?: number | null;
  unit?: string | null;
}
export interface Price {
  reporting_price: number;
  reporting_price_label: string;
  package_price?: number | null;
  normalized_unit_price?: number | null;
  regular_price?: number | null;
  discounted_price?: number | null;
  currency: string;
}
export interface Distribution {
  physical_store_distribution_count: number;
  service_area_presence_count: number;
  searched_store_count: number | null;
}
export interface Product {
  retailer_id: string;
  retailer_product_id: string;
  title: string;
  url: string | null;
  image_url: string | null;
  brand: string | null;
  brand_type: "private_label" | "regional" | "national" | "unclassified";
  seller_status: "qualified" | "unverified" | "not_qualified" | "not_applicable";
  package: Package;
  price: Price;
  distribution: Distribution;
}
export interface Comparison {
  comparison_basis: string;
  unit_basis: string;
  /**
   * Benchmark reporting price minus competitor reporting price in the displayed unit basis. Negative means the benchmark retailer is lower; positive means the competitor is lower.
   */
  price_delta: number;
  /**
   * price_delta divided by the competitor reporting price. Negative means the benchmark retailer is lower as a share of the competitor price; positive means the competitor is lower.
   */
  price_delta_percent: number;
  outcome: "walmart_wins" | "competitor_wins" | "parity" | "unscored";
  match_certification: MatchCertification;
}
export interface MatchCertification {
  status: "certified_comparable" | "certified_not_comparable" | "insufficient_evidence" | "pending";
  source: "matching_v2_gold_set" | "manual_review" | "legacy_governed" | "not_applicable";
}
export interface EvidenceRef {
  kind:
    | "search_observation"
    | "pdp_snapshot"
    | "match_decision"
    | "product_pack"
    | "retailer_pack"
    | "materialized_document";
  id: string;
}
export interface ExcludedRelationship {
  relationship_id: string;
  benchmark_product_id: string;
  competitor_product_id: string;
  competitor_retailer_id: string;
  reason_code: string;
  reason: string;
  evidence_refs?: EvidenceRef[];
}
export interface Qa {
  included_relationship_count: number;
  excluded_relationship_count: number;
  invalid_price_record_count: number;
  unverified_seller_product_count: number;
  products_without_image_count: number;
  products_without_valid_distribution_count: number;
  match_certification_complete: boolean;
  product_pack_coverage_status: "passed" | "passed_with_exclusions" | "blocked";
  retailer_coverage_status: "passed" | "passed_with_exclusions" | "blocked";
}
