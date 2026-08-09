/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceHistoricalInputManifest {
  schema_version: "1.0.0";
  stable_key: string;
  name: string;
  captured_at: string;
  product_pack: ProductPackReference;
  analysis_config: AnalysisConfig;
  /**
   * @minItems 1
   * @maxItems 100
   */
  artifacts: [Artifact, ...Artifact[]];
  metadata?: {
    [k: string]: unknown;
  };
}
export interface ProductPackReference {
  id: string;
  version: string;
}
export interface AnalysisConfig {
  id: string;
  name: string;
  version: string;
  benchmark_retailer: string;
  product_pack: ProductPackReference;
  /**
   * @minItems 1
   */
  retailers: [
    {
      retailer_id: string;
      enabled: boolean;
      [k: string]: unknown;
    },
    ...{
      retailer_id: string;
      enabled: boolean;
      [k: string]: unknown;
    }[]
  ];
  analysis: {
    comparison_profiles: string[];
    [k: string]: unknown;
  };
  delivery: {
    [k: string]: unknown;
  };
  [k: string]: unknown;
}
export interface Artifact {
  ordinal: number;
  retailer_id: string;
  adapter_id: "historical_metricscart_search_monitor_csv" | "historical_metricscart_consolidated_serp_csv";
  source_name: string;
  source_format: "metricscart_search_monitor_csv" | "metricscart_consolidated_serp_csv";
  content_type: "text/csv";
  expected_sha256: string;
  expected_rows: number;
}
