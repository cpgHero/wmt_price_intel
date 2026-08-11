/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceProductPackDraft {
  schema_version: "1.0.0";
  id: string;
  product_pack_id: string;
  base_version?: string | null;
  proposed_version: string;
  status: "draft" | "validating" | "candidate" | "certified" | "published" | "abandoned";
  revision: number;
  /**
   * Mutable authoring state; candidate validation applies the normative Product Pack contract.
   */
  config: {
    [k: string]: unknown;
  };
  /**
   * Mutable authoring state; candidate validation applies the normative report-blueprint contract.
   */
  report_blueprint: {
    [k: string]: unknown;
  };
  validation_summary?: {
    status: "not_run" | "running" | "passed" | "failed";
    passed: number;
    failed: number;
    warnings: number;
    last_run_id?: string | null;
  };
  created_by: string;
  created_at: string;
  updated_at: string;
}
