/* Generated from the normative JSON Schema. Do not edit manually. */

export interface MetricsCartProductDetailCatalog {
  schema_version: string;
  provider: "metricscart";
  source: string;
  status:
    "configuration_only_response_fixtures_required" | "enabled_v1_with_fixtures" | "catalogued_with_provider_samples";
  /**
   * @minItems 1
   */
  endpoints: [
    {
      retailer_id: string;
      provider_retailer: string;
      domain: string;
      endpoint_id: string;
      contract_version: string;
      method: "GET";
      path: string;
      credits_per_successful_page: number;
      paid_calls_enabled: boolean;
      required_params: ("url" | "product_id" | "zipcode" | "store" | "fulfillment_type" | "shopping_type")[];
      /**
       * @minItems 1
       */
      supported_params: [
        "url" | "product_id" | "zipcode" | "store" | "fulfillment_type" | "shopping_type",
        ...("url" | "product_id" | "zipcode" | "store" | "fulfillment_type" | "shopping_type")[]
      ];
      default_params?: {
        url?: string;
        product_id?: string;
        zipcode?: string;
        store?: string;
        fulfillment_type?: string;
        shopping_type?: string;
      };
      identity_param?: "product_id" | "url";
      product_id_left_pad_width?: number;
    },
    ...{
      retailer_id: string;
      provider_retailer: string;
      domain: string;
      endpoint_id: string;
      contract_version: string;
      method: "GET";
      path: string;
      credits_per_successful_page: number;
      paid_calls_enabled: boolean;
      required_params: ("url" | "product_id" | "zipcode" | "store" | "fulfillment_type" | "shopping_type")[];
      /**
       * @minItems 1
       */
      supported_params: [
        "url" | "product_id" | "zipcode" | "store" | "fulfillment_type" | "shopping_type",
        ...("url" | "product_id" | "zipcode" | "store" | "fulfillment_type" | "shopping_type")[]
      ];
      default_params?: {
        url?: string;
        product_id?: string;
        zipcode?: string;
        store?: string;
        fulfillment_type?: string;
        shopping_type?: string;
      };
      identity_param?: "product_id" | "url";
      product_id_left_pad_width?: number;
    }[]
  ];
}
