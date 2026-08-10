import type { ProductEvidenceResponse } from "./api";

const columns = [
  "outcome",
  "zipcode",
  "benchmark_retailer",
  "benchmark_product_id",
  "benchmark_product_name",
  "benchmark_store",
  "benchmark_price",
  "competitor",
  "competitor_product_id",
  "competitor_product_name",
  "competitor_store",
  "competitor_price",
  "competitor_minus_benchmark",
] as const;

function csvCell(value: unknown) {
  const raw = value === null || value === undefined ? "" : String(value);
  const safe = /^[=+\-@]/.test(raw) ? `'${raw}` : raw;
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
