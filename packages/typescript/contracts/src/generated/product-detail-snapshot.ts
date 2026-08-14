/* Generated from the normative JSON Schema. Do not edit manually. */

export type RetailCompetitiveIntelligenceProductDetailSnapshot = {
  [k: string]: unknown;
} & {
  schema_version: "1.0.0";
  snapshot_id: string;
  canonical_product_id?: string | null;
  provider: "metricscart";
  retailer_id: string;
  endpoint: {
    endpoint_id: string;
    path: string;
    method: "GET";
    contract_version: string;
  };
  request_context: {
    product_id: string;
    url?: string | null;
    zipcode: string | null;
    store: string | null;
    fulfillment_type: string | null;
    request_checksum_sha256: string;
  };
  observed_at: string;
  http_status: number;
  billing: {
    billable: boolean;
    credits: number;
  };
  normalized?: {
    normalizer_version?: string;
    retailer_product_id: string;
    name: string;
    brand?: string | null;
    seller?: string | null;
    url?: string | null;
    description_short?: string | null;
    description_full?: string | null;
    category_path?: string | null;
    identifiers: {
      [k: string]: unknown;
    };
    specification: {
      [k: string]: unknown;
    };
    physical_properties?: {
      [k: string]: unknown;
    };
    variant_configuration?: {
      [k: string]: unknown;
    };
    price?: number | null;
    price_currency?: string | null;
    availability: {
      stock_available: boolean | null;
      pickup_available: boolean | null;
      stock_quantity?: number | null;
      pickup_store_id?: string | null;
      shipping_type?: string | null;
    };
    media?: {
      image_primary?: string | null;
      images?: string[];
      videos?: unknown[];
    };
    commerce?: {
      [k: string]: unknown;
    };
    fulfillment?: {
      [k: string]: unknown;
    };
    reviews?: {
      [k: string]: unknown;
    };
    demand?: {
      [k: string]: unknown;
    };
    content?: {
      [k: string]: unknown;
    };
    relationships?: {
      [k: string]: unknown;
    };
    source_context?: {
      [k: string]: unknown;
    };
    source_field_inventory?: string[];
    unmapped_source_fields?: string[];
    extras?: {
      [k: string]: unknown;
    };
  };
  failure?: {
    failure_class: string;
    message?: string;
    should_retry: boolean;
  };
  raw_artifact: {
    artifact_id: string;
    storage_uri: string;
    checksum_sha256: string;
    immutable: true;
  };
  source_authority: {
    serp_price_authoritative: true;
    serp_availability_authoritative: true;
    pdp_identity_authoritative: true;
    pdp_package_semantics_allowed: true;
  };
};
