/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceBrandWorkbench {
  schema_version: "1.0.0";
  analysis_id: string;
  product_pack_id: string;
  product_pack_version: string;
  revision_id?: string | null;
  revision: number;
  current_publication_revision_id?: string | null;
  future_application?: null | {
    revision_id: string;
    revision: number;
  };
  retailers: {
    id: string;
    name: string;
  }[];
  brands: Brand[];
  summary: {
    suggested: number;
    confirmed: number;
    rejected: number;
    unclassified: number;
  };
}
export interface Brand {
  retailer_id: string;
  normalized_brand: string;
  display_brand: string;
  role: "private_label" | "regional" | "national" | "unclassified";
  status: "suggested" | "confirmed" | "rejected" | "unclassified";
  origin: "product_pack" | "deterministic" | "user";
  reason?: string | null;
  observed_products: number;
  observed_locations: number;
  observed_zipcodes: number;
  location_share: number;
  distribution_tier: "single_location" | "concentrated" | "multi_market" | "broad";
  product_examples: {
    product_id: string;
    name: string;
    image_url?: string | null;
  }[];
}
