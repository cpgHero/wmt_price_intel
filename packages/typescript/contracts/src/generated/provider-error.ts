/* Generated from the normative JSON Schema. Do not edit manually. */

export interface NormalizedProviderError {
  success: false;
  provider: string;
  error?: string;
  failure_class:
    | "rate_limit"
    | "authentication"
    | "invalid_request"
    | "not_found"
    | "provider_5xx"
    | "network"
    | "timeout"
    | "parse_error"
    | "schema_drift"
    | "unknown";
  http_status?: number | null;
  should_retry: boolean;
  backoff_seconds?: number | null;
  raw_body_excerpt?: string | null;
}
