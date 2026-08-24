/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceRetailerPack {
  schema_version: "1.0.0";
  id: string;
  display_name: string;
  version: string;
  status: "active" | "catalogued" | "needs_verification";
  identity: {
    canonical_retailer_id: string;
    aliases: string[];
  };
  observation_semantics: {
    price_authority: "search_location_observation";
    availability_authority: "search_location_observation";
    location_dimension: "store_zip" | "zipcode" | "pending_verification";
    physical_store_reporting: boolean;
    notes?: string[];
  };
  brand_foundation: {
    id: string;
    version: string;
  };
  brand_policy: {
    resolution_order: (
      | ["retailer_context", "exact_canonical", "exact_alias", "unresolved"]
      | [
          "retailer_context",
          "retailer_exact_canonical",
          "retailer_exact_alias",
          "global_exact_canonical",
          "global_exact_alias",
          "unresolved"
        ]
    ) &
      unknown[];
    strict_private_label_requires: (
      | ["in_private_label_matching", "approved_review", "eligible_status", "eligible_class"]
      | ["in_private_label_matching", "approved_review", "eligible_status", "eligible_class", "retailer_owned"]
    ) &
      unknown[];
    /**
     * @minItems 1
     */
    eligible_statuses: ["Active" | "Transitioning" | "Seasonal", ...("Active" | "Transitioning" | "Seasonal")[]];
    /**
     * @minItems 1
     */
    eligible_classes: [
      "private_label_owned" | "private_label_exclusive" | "retailer_banner_brand" | "sub_brand",
      ...("private_label_owned" | "private_label_exclusive" | "retailer_banner_brand" | "sub_brand")[]
    ];
    unknown_behavior: "queue_candidate_never_auto_approve";
    fuzzy_behavior: "suggestion_only_within_retailer";
    verified_private_labels?: {
      brand_name: string;
      aliases: string[];
      category_tags: string;
      evidence_notes: string;
    }[];
  };
  enrichment_policy: {
    identity_scope: "unique_admitted_products";
    default_contexts_per_product: 1;
    price_variant_context_policy: "additional_observed_context_on_price_difference";
    search_fields_are_immutable: true;
    default_cache_ttl_days?: number;
  };
  seller_policy?: {
    [k: string]: unknown;
  };
  matching_boundary: {
    brand_role: "candidate_generation_only";
    requires_product_pack_compatibility: true;
  };
}
