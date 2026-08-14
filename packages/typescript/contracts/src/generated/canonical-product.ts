/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceCanonicalProduct {
  schema_version: "1.0.0";
  canonical_product_id: string;
  retailer_id: string;
  retailer_product_id: string;
  /**
   * @minItems 1
   */
  identifiers: [
    {
      scheme:
        | "retailer_product_id"
        | "product_id"
        | "item_id"
        | "asin"
        | "upc"
        | "gtin"
        | "gtin13"
        | "model"
        | "sku"
        | "other";
      value: string;
      issuer?: string;
      primary: boolean;
    },
    ...{
      scheme:
        | "retailer_product_id"
        | "product_id"
        | "item_id"
        | "asin"
        | "upc"
        | "gtin"
        | "gtin13"
        | "model"
        | "sku"
        | "other";
      value: string;
      issuer?: string;
      primary: boolean;
    }[]
  ];
  identity: {
    name: string;
    brand?: string | null;
    seller?: string | null;
    url: string;
    image_primary?: string | null;
    description_short?: string | null;
    description_full?: string | null;
    category_path?: string | null;
    model_number?: string | null;
    item_condition?: string | null;
    specification: {
      [k: string]: unknown;
    };
    physical_properties?: {
      [k: string]: unknown;
    };
    variant_configuration?: {
      [k: string]: unknown;
    };
  };
  classification?: {
    product_pack_id: string;
    product_pack_version: string;
    in_scope: boolean;
    attributes: {
      [k: string]: unknown;
    };
    review_reasons?: string[];
  };
  /**
   * @minItems 1
   */
  source_contexts: [
    {
      source: "serp" | "pdp" | "historical_import" | "manual_validation";
      zipcode?: string | null;
      store_number?: string | null;
      fulfillment_type?: string | null;
      source_artifact_id?: string;
      observed_at: string;
    },
    ...{
      source: "serp" | "pdp" | "historical_import" | "manual_validation";
      zipcode?: string | null;
      store_number?: string | null;
      fulfillment_type?: string | null;
      source_artifact_id?: string;
      observed_at: string;
    }[]
  ];
  pdp_snapshot_ids: string[];
  provenance: {
    identity_checksum_sha256: string;
    created_at: string;
    updated_at: string;
  };
}
