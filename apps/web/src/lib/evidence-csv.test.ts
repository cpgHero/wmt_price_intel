import { describe, expect, it } from "vitest";

import type { ProductEvidenceResponse } from "./api";
import { productEvidenceCsv, productEvidenceFilename } from "./evidence-csv";

function evidence(): ProductEvidenceResponse {
  return {
    analysis_id: "analysis/id",
    publication_id: "publication-1",
    publication_version: 1,
    decision: null,
    decision_id: "decision-1",
    comparison_grain: "store",
    price_source: "search",
    attribute_source: "product pack",
    summary: {},
    rows: [
      {
        id: "row-1",
        outcome: "competitor_lower",
        zipcode: "00501",
        benchmark_retailer: "walmart_us",
        benchmark_product_id: "123",
        benchmark_product_name: '=unsafe "name"',
        benchmark_store: "0042",
        benchmark_price: 5.99,
        competitor: "aldi_us",
        competitor_product_id: "456",
        competitor_product_name: "Safe name",
        competitor_store: "475-001",
        competitor_price: 4.99,
        competitor_minus_benchmark: -1,
      },
    ],
  };
}

describe("productEvidenceCsv", () => {
  it("preserves identifiers and prevents spreadsheet formula injection", () => {
    const csv = productEvidenceCsv(evidence());

    expect(csv).toContain('"00501"');
    expect(csv).toContain('"0042"');
    expect(csv).toContain('"\'=unsafe ""name"""');
  });

  it("creates a safe download filename", () => {
    expect(productEvidenceFilename(evidence())).toBe(
      "analysis-id-decision-1-store-evidence.csv",
    );
  });
});
