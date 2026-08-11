/* Generated from the normative JSON Schema. Do not edit manually. */

/**
 * @minItems 1
 */
export type Capabilities = [
  {
    id: string;
    label: string;
    description: string;
    status: "available" | "deprecated" | "unavailable";
  },
  ...{
    id: string;
    label: string;
    description: string;
    status: "available" | "deprecated" | "unavailable";
  }[]
];

export interface RetailCompetitiveIntelligenceProductPackCapabilities {
  schema_version: "1.0.0";
  attribute_data_types: Capabilities;
  attribute_roles: Capabilities;
  extraction_rules: Capabilities;
  geographies: Capabilities;
  brand_policies: Capabilities;
  unknown_policies: Capabilities;
  price_selection_policies: Capabilities;
  package_equivalence_policies: Capabilities;
  report_sections: Capabilities;
  visualizations: Capabilities;
}
