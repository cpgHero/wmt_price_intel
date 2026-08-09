/* Generated from the normative JSON Schema. Do not edit manually. */

export type Topic =
  | "data_scope"
  | "footprint"
  | "exact_price"
  | "normalized_price"
  | "segment_drivers"
  | "segment_reversals"
  | "geography"
  | "fulfillment"
  | "brand_assortment"
  | "actions"
  | "caveats";

export interface RetailCompetitiveIntelligenceNarrativeBenchmarks {
  schema_version: "1.0.0";
  methodology_source: {
    filename: string;
    sha256: string;
  };
  categories: {
    [k: string]: Category;
  };
  /**
   * @minItems 1
   */
  quality_rubric: [
    {
      id: string;
      description: string;
      weight: number;
    },
    ...{
      id: string;
      description: string;
      weight: number;
    }[]
  ];
}
export interface Category {
  product_pack_id: string;
  /**
   * @minItems 3
   */
  sources: [Source, Source, Source, ...Source[]];
  /**
   * @minItems 1
   */
  required_topics: [Topic, ...Topic[]];
  /**
   * @minItems 1
   */
  required_story_patterns: [
    {
      id: string;
      description: string;
    },
    ...{
      id: string;
      description: string;
    }[]
  ];
}
export interface Source {
  kind: "xlsx" | "html" | "email";
  filename: string;
  sha256: string;
}
