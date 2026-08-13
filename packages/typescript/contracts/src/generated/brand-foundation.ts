/* Generated from the normative JSON Schema. Do not edit manually. */

export type RetailCompetitiveIntelligenceBrandFoundation = {
  [k: string]: unknown;
} & {
  schema_version: "1.0.0" | "2.0.0";
  id: string;
  name: string;
  version: string;
  status: "active" | "superseded";
  /**
   * @minItems 1
   */
  source_artifacts: [
    {
      name: string;
      sha256: string;
      role: "authoritative_master" | "authoritative_aliases" | "review_view" | "instructions";
    },
    ...{
      name: string;
      sha256: string;
      role: "authoritative_master" | "authoritative_aliases" | "review_view" | "instructions";
    }[]
  ];
  retailer_id_map: {
    [k: string]: string;
  };
  /**
   * @minItems 1
   */
  brands: [Brand, ...Brand[]];
  aliases: Alias[];
  external_brands?: ExternalBrand[];
  priority_brand_ids?: string[];
  retailer_presence?: RetailerPresence[];
  source_registry?: SourceRegistry[];
  agent_instructions?: AgentInstruction[];
  alias_conflicts?: AliasConflict[];
};

export interface Brand {
  brand_id: string;
  source_retailer_id: string;
  retailer_id: string;
  retailer: string;
  retailer_parent: string;
  brand_name: string;
  brand_name_normalized: string;
  brand_family: string;
  brand_bucket: "Private Label" | "Retailer-Associated" | "Regional" | "National" | "Candidate/Unknown";
  brand_class:
    | "private_label_owned"
    | "private_label_exclusive"
    | "retailer_banner_brand"
    | "sub_brand"
    | "acquired_brand"
    | "exclusive_partner_brand"
    | "regional_brand"
    | "national_brand"
    | "candidate_unknown";
  ownership_model: "retailer_owned" | "retailer_exclusive" | "exclusive_partnership" | "acquired_owned" | "unknown";
  in_private_label_matching: boolean;
  is_grocery_relevant: boolean;
  department_scope: string;
  category_tags: string;
  competitive_brand_role: string;
  positioning: string;
  status: "Active" | "Transitioning" | "Seasonal" | "Legacy" | "Candidate";
  retailer_exclusive: boolean;
  matching_priority: "High" | "Medium" | "Low";
  confidence: "Verified" | "High" | "Medium" | "Candidate";
  source_type: string;
  source_url: string;
  last_verified_at: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  review_status: "Approved" | "Pending" | "Rejected" | "Legacy Reference";
  notes: string;
}
export interface Alias {
  alias_id: string;
  source_alias_id: string;
  source_retailer_id: string;
  retailer_id: string;
  retailer: string;
  alias_name: string;
  alias_normalized: string;
  canonical_brand_id: string;
  canonical_brand_name: string;
  alias_type: string;
  status: "Active" | "Legacy";
  matching_rule: "exact_normalized" | "exact_normalized_then_category_gate" | "manual_or_legacy_map";
  confidence: "Verified" | "High" | "Medium" | "Candidate";
  source_url?: string | null;
  notes?: string | null;
  alias_namespace?: "private_label" | "regional_national";
  category_context?: string | null;
  source_reference?: string | null;
}
export interface ExternalBrand {
  brand_id: string;
  brand_name: string;
  brand_name_normalized: string;
  brand_bucket: "Regional" | "National";
  brand_class: "regional_brand" | "national_brand";
  owner_or_marketer: string;
  ownership_relationship: string;
  brand_family: string;
  priority_category: string;
  primary_category: string;
  category_tags: string;
  product_origin: string;
  distribution_scope: string;
  core_region: string | null;
  home_state: string | null;
  is_priority_brand: boolean;
  matching_priority: "Critical" | "High" | "Medium" | "Low";
  status: "Active" | "Transitioning" | "Seasonal" | "Legacy" | "Candidate";
  confidence: "Verified" | "High" | "Medium" | "Candidate";
  primary_source_id: string;
  corroborating_source_ids: string | null;
  source_type: string;
  source_url: string;
  last_verified_at: string | null;
  notes: string | null;
}
export interface RetailerPresence {
  brand_id: string;
  presence: {
    [k: string]: "UNKNOWN" | "PRESENT" | "ABSENT";
  };
  presence_rule: string;
  last_verified_at: string | null;
}
export interface SourceRegistry {
  source_id: string;
  organization: string;
  source_title: string;
  source_url: string;
  source_type: string;
  scope_supported: string;
  verified_at: string | null;
  evidence_notes: string | null;
}
export interface AgentInstruction {
  rule_id: string;
  topic: string;
  instruction: string;
}
export interface AliasConflict {
  retailer_id: string;
  alias_normalized: string;
  /**
   * @minItems 2
   */
  candidate_brand_ids: [string, string, ...string[]];
  resolution: "quarantined_unresolved";
}
