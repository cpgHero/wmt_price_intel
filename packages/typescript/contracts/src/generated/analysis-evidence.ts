/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceAnalysisEvidenceSet {
  schema_version: "1.0.0";
  evidence_set_id: string;
  analysis_id: string;
  kind:
    | "normalized_offers"
    | "classified_offers"
    | "product_catalog"
    | "exact_matches"
    | "compatible_matches"
    | "normalized_matches"
    | "proximity_matches"
    | "segment_metrics"
    | "exclusions"
    | "validation_issues";
  retailer_id?: string;
  competitor_id?: string;
  profile_id?: string;
  row_count: number;
  storage: {
    uri: string;
    content_type: "application/vnd.apache.parquet" | "application/json" | "application/gzip" | "text/csv";
    checksum_sha256: string;
    byte_size: number;
    partitioning?: string[];
  };
  /**
   * @minItems 1
   */
  columns: [
    {
      name: string;
      data_type: string;
      semantic_role: "identifier" | "dimension" | "measure" | "source_reference" | "quality_flag" | "descriptive";
      nullable: boolean;
      unit?: string;
    },
    ...{
      name: string;
      data_type: string;
      semantic_role: "identifier" | "dimension" | "measure" | "source_reference" | "quality_flag" | "descriptive";
      nullable: boolean;
      unit?: string;
    }[]
  ];
  lineage: {
    input_set_id: string;
    /**
     * @minItems 1
     */
    source_artifact_ids: [string, ...string[]];
    product_pack: {
      id: string;
      version: string;
      checksum_sha256: string;
    };
    analytics_code_version: string;
    generated_at: string;
  };
  access: {
    sensitivity: "internal" | "confidential";
    direct_download: boolean;
    max_preview_rows: number;
  };
  immutable: true;
}
