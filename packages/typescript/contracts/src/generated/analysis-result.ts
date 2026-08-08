/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceAnalysisResult {
  schema_version: string;
  analysis_id: string;
  collection_run_id: string;
  generated_at: string;
  benchmark_retailer: string;
  competitors?: string[];
  product_pack: {
    id: string;
    version: string;
  };
  source_summary: {
    [k: string]: unknown;
  };
  coverage: {
    [k: string]: unknown;
  }[];
  segments?: {
    [k: string]: unknown;
  }[];
  comparisons: {
    [k: string]: unknown;
  }[];
  data_quality: {
    [k: string]: unknown;
  };
  validation: {
    [k: string]: unknown;
  };
  findings?: {
    [k: string]: unknown;
  }[];
  recommendations?: {
    [k: string]: unknown;
  }[];
  artifacts?: {
    [k: string]: unknown;
  }[];
  provenance?: {
    [k: string]: unknown;
  };
}
