import type {
  CompetitiveProductCoverage,
  ProductEvidenceResponse,
} from "./api";

const columns = [
  "outcome",
  "zipcode",
  "benchmark_retailer",
  "benchmark_product_id",
  "benchmark_product_name",
  "benchmark_store",
  "raw_price_unit",
  "benchmark_price",
  "comparison_metric",
  "comparison_unit",
  "benchmark_comparison_value",
  "competitor",
  "competitor_product_id",
  "competitor_product_name",
  "competitor_store",
  "competitor_price",
  "competitor_comparison_value",
  "competitor_minus_benchmark",
  "comparison_gap",
] as const;

function csvCell(value: unknown) {
  const raw = value === null || value === undefined ? "" : String(value);
  const safe =
    typeof value === "string" && /^[=+\-@]/.test(raw) ? `'${raw}` : raw;
  return `"${safe.replaceAll('"', '""')}"`;
}

export function productEvidenceCsv(evidence: ProductEvidenceResponse) {
  return [
    columns.join(","),
    ...evidence.rows.map((row) =>
      columns.map((column) => csvCell(row[column])).join(","),
    ),
  ].join("\r\n");
}

export function productEvidenceFilename(evidence: ProductEvidenceResponse) {
  return `${evidence.analysis_id}-${evidence.decision_id}-store-evidence.csv`.replace(
    /[^A-Za-z0-9._-]/g,
    "-",
  );
}

const coverageColumns = [
  ["product_id", "product_id"],
  ["product_name", "product_name"],
  ["verified_local_locations", "observed_locations"],
  ["status", "status"],
  ["certified_relationships", "certified_relationships"],
  ["selected_price_basis_relationships", "selected_price_basis_relationships"],
  ["selected_competitor_products", "selected_competitor_products"],
  ["scored_product_locations", "scored_product_locations"],
] as const satisfies ReadonlyArray<
  readonly [string, keyof CompetitiveProductCoverage["products"][number]]
>;

export function competitiveProductCoverageCsv(
  coverage: CompetitiveProductCoverage,
) {
  return [
    coverageColumns.map(([label]) => label).join(","),
    ...coverage.products.map((row) =>
      coverageColumns.map(([, key]) => csvCell(row[key])).join(","),
    ),
  ].join("\r\n");
}

export function competitiveProductCoverageFilename(
  coverage: CompetitiveProductCoverage,
) {
  return `${coverage.analysis_id}-${coverage.competitor.id}-${coverage.profile_id}-${coverage.radius_miles}mi-product-coverage.csv`.replace(
    /[^A-Za-z0-9._-]/g,
    "-",
  );
}
