/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceProductPackValidationResult {
  schema_version: "1.0.0";
  id: string;
  draft_id: string;
  draft_revision: number;
  draft_checksum: string;
  suite: "quick" | "compact" | "full" | "publication";
  status: "queued" | "running" | "passed" | "failed" | "cancelled";
  gates: {
    id: string;
    label: string;
    status: "passed" | "failed" | "warning" | "not_run";
    message: string;
    details?: {
      [k: string]: unknown;
    };
  }[];
  engine_version?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
}
