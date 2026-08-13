/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligencePriceObservation {
  schema_version: "1.0.0";
  observation_id: string;
  analysis_id: string;
  product_pack_id: string;
  retailer_id: string;
  retailer_product_id: string;
  product_name: string;
  brand?: string | null;
  brand_type: "private_label" | "regional" | "national" | "unclassified";
  brand_origin: "user" | "product_pack" | "retailer_pack" | "search" | "pdp" | "unresolved";
  location: {
    scope_key: string;
    kind: "store" | "service_area";
    store_number?: string | null;
    store_name?: string | null;
    zipcode: string | null;
    city?: string | null;
    state?: string | null;
    country: string;
    latitude?: number | null;
    longitude?: number | null;
  };
  price: number | null;
  currency: string;
  in_stock?: boolean | null;
  observed_at: string | null;
  source_authority: "search_location_observation";
  eligible: boolean;
  exclusion_reasons?: string[];
}
