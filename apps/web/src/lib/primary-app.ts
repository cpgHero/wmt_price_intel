import type {
  AlertDefinitionRecord,
  AnalysisRecord,
  CollectionDefinitionRecord,
  JsonObject,
  RunRecord,
} from "./api";
import { asObject, displayLabel } from "./presentation";

export type QualityTier = "blocked" | "review_required" | "caveat" | "ready";

export interface QualityIssueSummary {
  key: string;
  label: string;
  count: number;
  rate: number | null;
  impact: string;
  severity: "blocker" | "review" | "warning";
}

export interface QualitySummary {
  tier: QualityTier;
  label: string;
  description: string;
  sourceRows: number | null;
  issues: QualityIssueSummary[];
  totalIssues: number;
}

export interface AnalysisSummary {
  analysis: AnalysisRecord;
  category: string;
  benchmarkRetailer: string;
  competitors: string[];
  observedAt: string;
  sourceRows: number | null;
  sourceScope: string;
  quality: QualitySummary;
}

export interface DefinitionSummary {
  definition: CollectionDefinitionRecord;
  productPackId: string;
  productPackVersion: string | null;
  benchmarkRetailer: string;
  retailers: string[];
  keyword: string | null;
  geography: string;
  schedule: string;
}

const QUALITY_LABELS: Record<string, string> = {
  blocker: "Blocking quality issues",
  blockers: "Blocking quality issues",
  normalization_rejections: "Normalization exclusions",
  review_offers: "Products awaiting classification review",
  warning: "Quality warnings",
  warnings: "Quality warnings",
  zero_or_missing_price_offers: "Missing or zero-price observations",
};

const QUALITY_IMPACT: Record<string, string> = {
  blocker: "These issues can prevent the analysis from supporting a decision.",
  blockers: "These issues can prevent the analysis from supporting a decision.",
  normalization_rejections:
    "These observations were excluded from normalized price comparisons.",
  review_offers:
    "These products need classification review before they can support complete assortment conclusions.",
  warning:
    "These findings remain usable only with the accompanying quality caveat.",
  warnings:
    "These findings remain usable only with the accompanying quality caveat.",
  zero_or_missing_price_offers:
    "These observations were excluded from price conclusions because no usable price was captured.",
};

function numericValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function stringValues(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function totalSourceRows(result: JsonObject): number | null {
  const source = asObject(result.source);
  const sourceSummary = asObject(result.source_summary);
  return (
    numericValue(source.total_rows) ?? numericValue(sourceSummary.total_rows)
  );
}

function issueSeverity(key: string): QualityIssueSummary["severity"] {
  if (key.includes("block") || key.includes("fail")) return "blocker";
  if (key.includes("review") || key.includes("ambiguous")) return "review";
  return "warning";
}

function issueCounts(quality: JsonObject): Array<[string, number]> {
  const nested = asObject(quality.issue_counts);
  const source = Object.keys(nested).length > 0 ? nested : quality;
  return Object.entries(source)
    .map(([key, value]) => [key, numericValue(value)] as const)
    .filter(
      (entry): entry is [string, number] => entry[1] !== null && entry[1] > 0,
    )
    .filter(([key]) => !["metric_reference_coverage", "status"].includes(key));
}

export function summarizeQuality(analysis: AnalysisRecord): QualitySummary {
  const result = asObject(analysis.result);
  const quality = asObject(result.data_quality);
  const validation = asObject(result.validation);
  const sourceRows = totalSourceRows(result);
  const counts = issueCounts(quality);
  const status =
    `${String(quality.status ?? "")} ${String(validation.status ?? "")}`.toLowerCase();
  const blocking =
    counts.some(([key]) => issueSeverity(key) === "blocker") ||
    /blocked|failed|invalid|error/.test(status);
  const reviewRequired =
    counts.some(([key]) => issueSeverity(key) === "review") ||
    /review_required|needs_review/.test(status);
  const caveat = counts.length > 0 || /warning|caveat/.test(status);
  const tier: QualityTier = blocking
    ? "blocked"
    : reviewRequired
      ? "review_required"
      : caveat
        ? "caveat"
        : "ready";
  const issues = counts
    .map(([key, count]): QualityIssueSummary => ({
      key,
      label: QUALITY_LABELS[key] ?? displayLabel(key),
      count,
      rate: sourceRows && sourceRows > 0 ? count / sourceRows : null,
      impact:
        QUALITY_IMPACT[key] ??
        "Review the affected records before extending the conclusion beyond validated evidence.",
      severity: issueSeverity(key),
    }))
    .sort((left, right) => {
      const order = { blocker: 0, review: 1, warning: 2 } as const;
      return (
        order[left.severity] - order[right.severity] || right.count - left.count
      );
    });
  const labels: Record<QualityTier, [string, string]> = {
    blocked: [
      "Blocked",
      "One or more quality failures must be resolved before this analysis should support a decision.",
    ],
    review_required: [
      "Review required",
      "The analysis contains unresolved records that can materially limit assortment or matching conclusions.",
    ],
    caveat: [
      "Ready with caveats",
      "Validated findings are available, with explicitly excluded or incomplete source observations.",
    ],
    ready: [
      "Ready",
      "No material quality issue is currently recorded for this analysis.",
    ],
  };
  return {
    tier,
    label: labels[tier][0],
    description: labels[tier][1],
    sourceRows,
    issues,
    totalIssues: issues.reduce((sum, issue) => sum + issue.count, 0),
  };
}

export function summarizeAnalysis(analysis: AnalysisRecord): AnalysisSummary {
  const result = asObject(analysis.result);
  const source = asObject(result.source);
  const sourceSummary = asObject(result.source_summary);
  const productPack = asObject(result.product_pack);
  const competitors = stringValues(result.competitors).map(displayLabel);
  const sampling = Boolean(source.sampling ?? sourceSummary.sampling);
  return {
    analysis,
    category: displayLabel(String(productPack.id ?? analysis.product_pack_id)),
    benchmarkRetailer: displayLabel(
      String(result.benchmark_retailer ?? "walmart_us"),
    ),
    competitors,
    observedAt: String(
      source.observed_end ?? result.generated_at ?? analysis.created_at,
    ),
    sourceRows: totalSourceRows(result),
    sourceScope: sampling ? "Sampled collection" : "Full collection scope",
    quality: summarizeQuality(analysis),
  };
}

export function summarizeDefinition(
  definition: CollectionDefinitionRecord,
): DefinitionSummary {
  const config = definition.config;
  const productPack = asObject(config.product_pack);
  const query = asObject(config.query);
  const geography = asObject(config.geography);
  const schedule = asObject(config.schedule);
  const retailerRows = Array.isArray(config.retailers)
    ? config.retailers.map(asObject).filter((row) => row.enabled !== false)
    : [];
  const zipcodes = stringValues(geography.zipcodes);
  const states = stringValues(geography.states);
  const strategy = String(geography.strategy ?? "configured geography");
  let geographyLabel = displayLabel(strategy);
  if (zipcodes.length > 0) {
    geographyLabel = `${zipcodes.length.toLocaleString()} ZIP${zipcodes.length === 1 ? "" : "s"}`;
  } else if (states.length > 0) {
    geographyLabel = `${states.length.toLocaleString()} state${states.length === 1 ? "" : "s"}`;
  }
  const scheduleType = String(schedule.type ?? "manual");
  return {
    definition,
    productPackId: String(productPack.id ?? "unknown_product_pack"),
    productPackVersion:
      typeof productPack.version === "string" ? productPack.version : null,
    benchmarkRetailer: displayLabel(
      String(
        config.benchmark_retailer ??
          geography.benchmark_retailer ??
          "walmart_us",
      ),
    ),
    retailers: retailerRows.map((row) =>
      displayLabel(String(row.retailer_id ?? "retailer")),
    ),
    keyword: typeof query.keyword === "string" ? query.keyword : null,
    geography: geographyLabel,
    schedule:
      scheduleType === "manual"
        ? "Manual"
        : `Scheduled in ${String(schedule.timezone ?? "UTC")}`,
  };
}

export function definitionForRun(
  run: RunRecord,
  definitions: CollectionDefinitionRecord[],
): DefinitionSummary | null {
  const definition = definitions.find(
    (candidate) => candidate.version_id === run.definition_version_id,
  );
  return definition ? summarizeDefinition(definition) : null;
}

export function isActiveRun(run: RunRecord): boolean {
  return ["queued", "running", "cancelling"].includes(run.status);
}

export function isInternalAcceptanceRecord(value: string): boolean {
  const normalized = value.toLowerCase();
  return normalized.includes("phase09") || normalized.includes("phase 09");
}

export function describeAlertCondition(alert: AlertDefinitionRecord): string {
  const condition = asObject(alert.config.condition);
  const selector = asObject(alert.config.selector);
  const field = String(selector.field ?? "the selected metric");
  const threshold = String(condition.threshold ?? "the configured threshold");
  const operator = String(condition.operator ?? "changes");
  const operatorLabels: Record<string, string> = {
    change_gte: "changes by at least",
    eq: "equals",
    gt: "rises above",
    gte: "reaches at least",
    lt: "falls below",
    lte: "reaches no more than",
  };
  const mode = condition.change_mode === "percent" ? "%" : "";
  return `Notify when ${displayLabel(field).toLowerCase()} ${operatorLabels[operator] ?? displayLabel(operator).toLowerCase()} ${threshold}${mode}.`;
}
