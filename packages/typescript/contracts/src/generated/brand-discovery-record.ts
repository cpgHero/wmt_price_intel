/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceBrandDiscoveryRecord {
  schema_version: "1.0.0";
  queue_id: string;
  observed_retailer_id: string;
  observed_brand_raw: string;
  observed_brand_normalized: string;
  observed_product_title?: string | null;
  observed_url?: string | null;
  observed_domain: string;
  observed_at: string;
  source_collection: string;
  source_job_id?: string | null;
  proposed_brand_bucket: "Candidate/Unknown";
  proposed_brand_class: "candidate_unknown";
  proposed_canonical_brand_id?: string | null;
  /**
   * @minItems 1
   */
  evidence_type: [
    (
      | "retailer_corporate_brand_page"
      | "first_party_pdp_legal_signal"
      | "multiple_first_party_pdp_exclusivity"
      | "credible_secondary"
      | "isolated_search_observation"
    ),
    ...(
      | "retailer_corporate_brand_page"
      | "first_party_pdp_legal_signal"
      | "multiple_first_party_pdp_exclusivity"
      | "credible_secondary"
      | "isolated_search_observation"
    )[]
  ];
  evidence_count: number;
  exclusivity_signal: true | false | "unknown";
  distributor_signal?: string | null;
  retailer_brand_page_signal: boolean;
  first_party_source_url?: string | null;
  confidence_score: number;
  duplicate_candidate_of?: string | null;
  review_status: "Pending" | "Approved" | "Rejected" | "Needs Evidence";
  reviewer?: string | null;
  reviewed_at?: string | null;
  decision?:
    | null
    | "map_existing"
    | "create_private_label"
    | "create_regional"
    | "create_national"
    | "reject"
    | "needs_evidence";
  decision_notes?: string | null;
}
