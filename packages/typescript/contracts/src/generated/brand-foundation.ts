/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceBrandFoundation {
  schema_version: "1.0.0";
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
}
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
  matching_rule: "exact_normalized" | "manual_or_legacy_map";
  confidence: "Verified" | "High" | "Medium" | "Candidate";
  source_url?: string | null;
  notes?: string | null;
}
