/* Generated from the normative JSON Schema. Do not edit manually. */

export type Selector =
  | {
      type: "json_path";
      /**
       * @minItems 1
       */
      path: [string | number, ...(string | number)[]];
    }
  | {
      type: "list_filter";
      /**
       * @minItems 1
       */
      path: [string | number, ...(string | number)[]];
      where: {
        [k: string]: unknown;
      };
      field: string;
    }
  | {
      type: "row_filter";
      where: {
        [k: string]: unknown;
      };
      field: string;
    }
  | {
      type: "aggregate";
      operation: "sum";
      field: string;
    }
  | {
      type: "ratio_of_sums";
      numerator_field: string;
      denominator_field: string;
    };

export interface RetailCompetitiveIntelligenceGoldenBenchmarks {
  schema_version: string;
  purpose?: string;
  categories: {
    [k: string]: Category;
  };
}
export interface Category {
  dataset_id: string;
  source_rows: number;
  /**
   * @minItems 1
   */
  assertions: [Assertion, ...Assertion[]];
}
export interface Assertion {
  name: string;
  source: string;
  source_format: "json" | "csv";
  selector: Selector;
  expected: number;
  tolerance_abs: number;
}
