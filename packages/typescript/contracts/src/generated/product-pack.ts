/* Generated from the normative JSON Schema. Do not edit manually. */

export interface RetailCompetitiveIntelligenceProductPack {
  id: string;
  name: string;
  version: string;
  category_family: string;
  description?: string;
  scope: {
    include: string[];
    exclude: string[];
    hard_exclusion_patterns?: string[];
    /**
     * @minItems 1
     */
    target_terms?: [string, ...string[]];
    availability_policy?: "search_presence" | "in_stock_only" | "retailer_specific";
    require_positive_price?: boolean;
    [k: string]: unknown;
  };
  attributes: {
    name: string;
    label?: string;
    data_type: "string" | "number" | "boolean" | "enum" | "array";
    role: "identity" | "matching" | "normalization" | "reporting" | "qa";
    required_for_strict?: boolean;
    allowed_values?: unknown[];
    unknown_values?: unknown[];
    synonyms?: {
      [k: string]: unknown;
    };
    unit?: string;
    unknown_policy?: "reject_strict" | "allow_compatible" | "infer" | "review" | "not_applicable";
    extractors?: (
      "title_rule" | "url_rule" | "retailer_field" | "cross_product_inference" | "ai_fallback" | "manual"
    )[];
    extraction_rules?: {
      type: "constant" | "field" | "measurement" | "number_pattern" | "term_map" | "boolean_terms";
      /**
       * @minItems 1
       */
      sources?: [string, ...string[]];
      value?: unknown;
      units?: {
        [k: string]: number;
      };
      /**
       * @minItems 1
       */
      patterns?: [string, ...string[]];
      group?: number;
      values?: {
        /**
         * @minItems 1
         */
        [k: string]: [string, ...string[]];
      };
      true_terms?: string[];
      false_terms?: string[];
      absence_policy?: "unknown" | "infer_default";
      default?: unknown;
    }[];
    [k: string]: unknown;
  }[];
  normalization: {
    primary_display_metric: string;
    secondary_metrics?: string[];
    conversion_rules?: {
      [k: string]: unknown;
    }[];
    forbidden_metrics?: string[];
    package_equivalence_policy?: "exact_package_first" | "unit_normalized_only" | "category_specific";
    [k: string]: unknown;
  };
  matching_profiles: {
    id: string;
    label: string;
    geography: "exact_zip" | "same_store_market" | "radius" | "national";
    radius_miles?: number;
    dimensions: string[];
    attribute_constraints?: {
      /**
       * @minItems 1
       */
      [k: string]: [unknown, ...unknown[]];
    };
    benchmark_attribute_constraints?: {
      /**
       * @minItems 1
       */
      [k: string]: [unknown, ...unknown[]];
    };
    competitor_attribute_constraints?: {
      /**
       * @minItems 1
       */
      [k: string]: [unknown, ...unknown[]];
    };
    brand_policy: "same_brand" | "private_label_equivalent" | "ignore_brand" | "category_specific";
    unknown_policy?: "reject" | "wildcard_if_one_unknown" | "allow" | "review";
    wildcard_dimensions?: string[];
    price_selection?: "lowest_positive" | "median" | "retailer_primary_offer";
    comparison_metric?: string;
    comparison_interval?: {
      low_metric: string;
      high_metric: string;
    };
    availability_policy?: "search_presence" | "in_stock_only" | "retailer_specific";
    relationship_scope_policy?: {
      default_scope_mode: "global" | "observed_benchmark_product_footprint" | "explicit_benchmark_locations";
      allow_scoped_reuse: boolean;
      relationship_role: "primary" | "alternative";
      conflict_behavior: "exclude_from_price_comparison";
      comparison_context_grain: "benchmark_location" | "benchmark_zip";
      minimum_locations?: number;
      future_location_policy?: "require_review" | "inherit_observed_footprint";
    };
    [k: string]: unknown;
  }[];
  brand_rules?: {
    aliases?: {
      [k: string]: string[];
    };
    private_labels?: {
      /**
       * @minItems 1
       */
      [k: string]: [string, ...string[]];
    };
    portfolios?: {
      id: string;
      label: string;
      role: "private_label" | "regional" | "national" | "unclassified";
      /**
       * @minItems 1
       */
      retailer_ids: [string, ...string[]];
      /**
       * @minItems 1
       */
      brands: [string, ...string[]];
      evidence_notes?: string;
    }[];
  };
  qa_rules: {
    parity_tolerance_dollars?: number;
    min_price?: number;
    max_price?: number;
    suspicious_gap_pct?: number;
    require_unit_confirmation_when?: string[];
    human_review_conditions?: string[];
    sensitivity_checks?: {
      [k: string]: unknown;
    }[];
    [k: string]: unknown;
  };
  retailer_overrides?: {
    [k: string]: unknown;
  };
  reporting: {
    headline_segments: string[];
    required_caveats: string[];
    recommended_charts?: string[];
    brand_portfolio_panels?: {
      id: string;
      label: string;
      profile_id: string;
      benchmark_portfolio_ids: string[];
      competitor_portfolio_ids: string[];
      question: string;
    }[];
    decision_rules?: {
      preferred_scorecard_profile_id: string;
      /**
       * @minItems 1
       */
      profile_priority: [string, ...string[]];
      minimum_observations: number;
      minimum_geographies: number;
      /**
       * @minItems 1
       */
      executive_relationship_states: ["suggested" | "confirmed", ...("suggested" | "confirmed")[]];
      extreme_gap_behavior: "review" | "suppress";
      parity_display: "include" | "hide_when_zero";
    };
    alertable_metrics?: string[];
    report_blueprint: {
      id: string;
      version: string;
    };
    narrative_playbook: {
      leadership_objective: string;
      /**
       * @minItems 1
       */
      required_topics: [
        (
          | "data_scope"
          | "footprint"
          | "exact_price"
          | "normalized_price"
          | "segment_drivers"
          | "segment_reversals"
          | "geography"
          | "fulfillment"
          | "brand_assortment"
          | "actions"
          | "caveats"
        ),
        ...(
          | "data_scope"
          | "footprint"
          | "exact_price"
          | "normalized_price"
          | "segment_drivers"
          | "segment_reversals"
          | "geography"
          | "fulfillment"
          | "brand_assortment"
          | "actions"
          | "caveats"
        )[]
      ];
      /**
       * @minItems 1
       */
      decision_lenses: [
        {
          id: string;
          label: string;
          question: string;
          /**
           * @minItems 1
           */
          metric_selectors: [string, ...string[]];
        },
        ...{
          id: string;
          label: string;
          question: string;
          /**
           * @minItems 1
           */
          metric_selectors: [string, ...string[]];
        }[]
      ];
      /**
       * @minItems 1
       */
      action_principles: [string, ...string[]];
      forbidden_claims: string[];
      small_sample_threshold: number;
      story_priorities?: {
        id: string;
        kind:
          | "competitive_pressure"
          | "benchmark_strength"
          | "mixed_position"
          | "segment_reversal"
          | "geographic_validation"
          | "action";
        headline: string;
        objective: string;
        /**
         * @minItems 1
         */
        topic_refs: [
          (
            | "data_scope"
            | "footprint"
            | "exact_price"
            | "normalized_price"
            | "segment_drivers"
            | "segment_reversals"
            | "geography"
            | "fulfillment"
            | "brand_assortment"
            | "actions"
            | "caveats"
          ),
          ...(
            | "data_scope"
            | "footprint"
            | "exact_price"
            | "normalized_price"
            | "segment_drivers"
            | "segment_reversals"
            | "geography"
            | "fulfillment"
            | "brand_assortment"
            | "actions"
            | "caveats"
          )[]
        ];
        /**
         * @minItems 1
         */
        section_ids: [string, ...string[]];
        competitor_ids?: string[];
        profile_ids?: string[];
        segment_scope?: "overall" | "segment" | "any";
        significances?: ("strength" | "watch" | "risk" | "caveat")[];
        segment_attribute_constraints?: {
          [k: string]: unknown;
        };
        max_facts: number;
      }[];
    };
    insight_ranking: {
      weights: {
        breadth: number;
        magnitude: number;
        confidence: number;
        actionability: number;
      };
      minimum_score: number;
      max_candidates: number;
    };
    /**
     * @minItems 1
     */
    insight_rules: [
      {
        id: string;
        scope: "overall" | "segment" | "both";
        condition: {
          field: string;
          operator: "gt" | "gte" | "lt" | "lte";
          threshold: number;
        };
        title_template: string;
        summary_template: string;
        business_impact: string;
        severity: "positive" | "info" | "watch" | "high" | "critical";
        breadth_scale: number;
        magnitude_scale: number;
        confidence_scale: number;
        actionability: number;
        minimum_matches?: number;
        limitations?: string[];
        recommendation?: {
          action_template: string;
          owner: string;
          rationale_template: string;
        };
      },
      ...{
        id: string;
        scope: "overall" | "segment" | "both";
        condition: {
          field: string;
          operator: "gt" | "gte" | "lt" | "lte";
          threshold: number;
        };
        title_template: string;
        summary_template: string;
        business_impact: string;
        severity: "positive" | "info" | "watch" | "high" | "critical";
        breadth_scale: number;
        magnitude_scale: number;
        confidence_scale: number;
        actionability: number;
        minimum_matches?: number;
        limitations?: string[];
        recommendation?: {
          action_template: string;
          owner: string;
          rationale_template: string;
        };
      }[]
    ];
  };
  regression?: {
    golden_dataset_ids?: string[];
    expected_headlines?: {
      [k: string]: unknown;
    }[];
    tolerances?: {
      [k: string]: unknown;
    };
    [k: string]: unknown;
  };
  [k: string]: unknown;
}
