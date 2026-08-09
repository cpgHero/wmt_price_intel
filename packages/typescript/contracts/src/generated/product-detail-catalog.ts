/* Generated from the normative JSON Schema. Do not edit manually. */

export interface MetricsCartProductDetailCatalog {
  schema_version: string;
  provider: "metricscart";
  source: string;
  status: "configuration_only_response_fixtures_required" | "enabled_v1_with_fixtures";
  /**
   * @minItems 1
   */
  endpoints: [
    {
      retailer_id: string;
      provider_retailer: string;
      domain: string;
      endpoint_id: string;
      method: "GET";
      path: string;
      credits_per_successful_page: number;
      required_params: ("url" | "product_id" | "zipcode" | "store" | "fulfillment_type")[];
      /**
       * @minItems 1
       */
      supported_params: [
        "url" | "product_id" | "zipcode" | "store" | "fulfillment_type",
        ...("url" | "product_id" | "zipcode" | "store" | "fulfillment_type")[]
      ];
    },
    ...{
      retailer_id: string;
      provider_retailer: string;
      domain: string;
      endpoint_id: string;
      method: "GET";
      path: string;
      credits_per_successful_page: number;
      required_params: ("url" | "product_id" | "zipcode" | "store" | "fulfillment_type")[];
      /**
       * @minItems 1
       */
      supported_params: [
        "url" | "product_id" | "zipcode" | "store" | "fulfillment_type",
        ...("url" | "product_id" | "zipcode" | "store" | "fulfillment_type")[]
      ];
    }[]
  ];
}
