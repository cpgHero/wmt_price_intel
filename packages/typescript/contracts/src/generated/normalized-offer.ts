/* Generated from the normative JSON Schema. Do not edit manually. */

export interface NormalizedRetailOffer {
  collection_run_id: string;
  task_id: string;
  provider: string;
  retailer_id: string;
  page: number;
  result_position: number | null;
  collected_at: string;
  query?: {
    [k: string]: unknown;
  };
  location: {
    retailer_location_id?: string | null;
    store_number?: string | null;
    zipcode: string;
    latitude?: number | null;
    longitude?: number | null;
    country?: string | null;
  };
  product: {
    name: string;
    brand?: string | null;
    retailer_product_id: string;
    identifiers?: {
      [k: string]: unknown;
    };
    url?: string | null;
    image_primary?: string | null;
    is_sponsored?: boolean | null;
    rating?: number | null;
    rating_count?: number | null;
    reviews_count?: number | null;
  };
  price: {
    raw?: string | null;
    current: number | null;
    regular?: number | null;
    discounted?: number | null;
    currency: string;
  };
  availability: {
    stock_available?: boolean | null;
    pickup_available?: boolean | null;
    pickup_store_id?: string | null;
    pickup_zipcode?: string | null;
    pickup_address?: string | null;
    shipping_type?: string | null;
    shipping_delivery_zipcode?: string | null;
    shipping_expected_delivery_date?: string | null;
    pickup_extras?: {
      [k: string]: unknown;
    };
    shipping_extras?: {
      [k: string]: unknown;
    };
  };
  raw_extra?: {
    [k: string]: unknown;
  };
}
