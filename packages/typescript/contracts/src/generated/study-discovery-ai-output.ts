/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceStudyDiscoveryAISuggestion {
  kind: "query_plan" | "product_pack_hypothesis";
  summary: string;
  suggestions: {
    keyword?: string | null;
    /**
     * @maxItems 8
     */
    alternate_queries?:
      | []
      | [string]
      | [string, string]
      | [string, string, string]
      | [string, string, string, string]
      | [string, string, string, string, string]
      | [string, string, string, string, string, string]
      | [string, string, string, string, string, string, string]
      | [string, string, string, string, string, string, string, string];
    /**
     * @maxItems 40
     */
    target_terms?: string[];
    /**
     * @maxItems 80
     */
    exclusion_terms?: string[];
    /**
     * @maxItems 24
     */
    attribute_hypotheses?: {
      name: string;
      label: string;
      data_type: "string" | "number" | "boolean" | "enum";
      matching_relevance: "strict" | "normalized" | "identity" | "reporting_only";
      /**
       * @minItems 1
       * @maxItems 8
       */
      evidence:
        | [string]
        | [string, string]
        | [string, string, string]
        | [string, string, string, string]
        | [string, string, string, string, string]
        | [string, string, string, string, string, string]
        | [string, string, string, string, string, string, string]
        | [string, string, string, string, string, string, string, string];
    }[];
  };
  /**
   * @maxItems 30
   */
  unknowns: string[];
  /**
   * @minItems 1
   * @maxItems 30
   */
  required_human_checks: [string, ...string[]];
}
