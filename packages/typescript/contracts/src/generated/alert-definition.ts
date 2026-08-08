/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceAlertDefinition {
  id: string;
  name: string;
  enabled: boolean;
  scope: {
    product_pack_ids?: string[];
    collection_definition_ids?: string[];
  };
  metric: {
    /**
     * @minItems 1
     */
    path: [string | number, ...(string | number)[]];
    where?: {
      [k: string]: unknown;
    };
    field: string;
  };
  condition: {
    operator:
      "gt" | "gte" | "lt" | "lte" | "change_gt" | "change_gte" | "change_lt" | "change_lte" | "absolute_change_gte";
    threshold: number;
    change_mode?: "absolute" | "percentage_points" | "percent_change";
  };
  cooldown_minutes?: number;
  delivery: {
    /**
     * @minItems 1
     */
    email_recipients: [string, ...string[]];
  };
}
