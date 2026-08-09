/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceReportBlueprint {
  schema_version: "1.0.0";
  id: string;
  version: string;
  product_pack: {
    id: string;
    version: string;
  };
  brand_profile: {
    id: string;
    version: string;
    supports_light_mode: boolean;
    supports_dark_mode: boolean;
  };
  /**
   * @minItems 1
   */
  sections: [
    {
      id: string;
      title: string;
      kind:
        | "executive_summary"
        | "kpi_strip"
        | "coverage"
        | "price_position"
        | "segment_analysis"
        | "geographic_sensitivity"
        | "assortment"
        | "product_table"
        | "recommendations"
        | "data_quality"
        | "methodology";
      required: boolean;
      metric_selectors: string[];
      evidence_kinds: string[];
      visualization?: "none" | "kpi_cards" | "bar" | "stacked_bar" | "line" | "map" | "table" | "ranked_cards";
      empty_state?: string;
      narrative_section_id?: string;
    },
    ...{
      id: string;
      title: string;
      kind:
        | "executive_summary"
        | "kpi_strip"
        | "coverage"
        | "price_position"
        | "segment_analysis"
        | "geographic_sensitivity"
        | "assortment"
        | "product_table"
        | "recommendations"
        | "data_quality"
        | "methodology";
      required: boolean;
      metric_selectors: string[];
      evidence_kinds: string[];
      visualization?: "none" | "kpi_cards" | "bar" | "stacked_bar" | "line" | "map" | "table" | "ranked_cards";
      empty_state?: string;
      narrative_section_id?: string;
    }[]
  ];
  /**
   * @minItems 1
   */
  artifact_profiles: [
    {
      artifact_type: "html" | "xlsx" | "leadership_email" | "audit_zip";
      /**
       * @minItems 1
       */
      section_ids: [string, ...string[]];
      worksheet_definitions?: {
        name: string;
        source: string;
      }[];
    },
    ...{
      artifact_type: "html" | "xlsx" | "leadership_email" | "audit_zip";
      /**
       * @minItems 1
       */
      section_ids: [string, ...string[]];
      worksheet_definitions?: {
        name: string;
        source: string;
      }[];
    }[]
  ];
  narrative_policy: {
    require_metric_refs: true;
    require_evidence_refs: true;
    allow_unreferenced_numbers: false;
    /**
     * @minItems 1
     */
    required_questions: [
      "what_changed" | "why_it_matters" | "who_is_affected" | "what_to_do_next" | "what_is_the_evidence",
      ...("what_changed" | "why_it_matters" | "who_is_affected" | "what_to_do_next" | "what_is_the_evidence")[]
    ];
  };
}
