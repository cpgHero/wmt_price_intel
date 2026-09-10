#!/usr/bin/env node

import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(import.meta.url);

function usage() {
  return [
    "Usage:",
    "  node scripts/audit_canonical_report_dataset.mjs --input <dataset.json-or-url> [--output <audit.md>]",
    "",
    "Examples:",
    "  node scripts/audit_canonical_report_dataset.mjs --input examples/canonical-report-dataset.bananas.json",
    "  node scripts/audit_canonical_report_dataset.mjs --input http://localhost:3000/api/analyses/<id>/canonical-report-dataset --output /tmp/canonical-audit.md",
    "",
    "If dependencies are not linked in this checkout, set RCI_NODE_MODULES_FALLBACK to one or more node_modules search paths separated by ':'.",
  ].join("\n");
}

function argument(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : null;
}

function isUrl(value) {
  return /^https?:\/\//i.test(value);
}

async function loadText(input) {
  if (isUrl(input)) {
    const response = await fetch(input, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`GET ${input} returned HTTP ${response.status}`);
    }
    return await response.text();
  }
  const path = isAbsolute(input) ? input : join(repositoryRoot, input);
  return await readFile(path, "utf8");
}

async function loadJson(input) {
  try {
    return JSON.parse(await loadText(input));
  } catch (error) {
    throw new Error(`Could not parse ${input} as JSON: ${error.message}`);
  }
}

async function contractValidator() {
  let Ajv2020;
  let addFormats;
  try {
    const searchPaths = [
      join(
        repositoryRoot,
        "packages",
        "typescript",
        "contracts",
        "node_modules",
      ),
      join(repositoryRoot, "node_modules"),
      ...String(process.env.RCI_NODE_MODULES_FALLBACK ?? "")
        .split(":")
        .map((part) => part.trim())
        .filter(Boolean),
    ];
    const ajvPath = require.resolve("ajv/dist/2020.js", {
      paths: searchPaths,
    });
    const formatsPath = require.resolve("ajv-formats", {
      paths: searchPaths,
    });
    ({ default: Ajv2020 } = await import(pathToFileURL(ajvPath).href));
    ({ default: addFormats } = await import(pathToFileURL(formatsPath).href));
  } catch (error) {
    throw new Error(
      [
        "Canonical dataset audit requires linked Node dependencies: ajv and ajv-formats.",
        "Run `pnpm install --frozen-lockfile` in the repository, then retry.",
        `Original error: ${error.message}`,
      ].join("\n"),
    );
  }
  const ajv = new Ajv2020({
    allErrors: true,
    allowUnionTypes: true,
    strict: true,
  });
  addFormats(ajv);
  const schemaDir = join(repositoryRoot, "schemas");
  const schemaNames = (await readdir(schemaDir))
    .filter((name) => name.endsWith(".json"))
    .sort();
  for (const schemaName of schemaNames) {
    const schema = JSON.parse(
      await readFile(join(schemaDir, schemaName), "utf8"),
    );
    ajv.addSchema(schema, schemaName);
  }
  const validate = ajv.getSchema("canonical-report-dataset.schema.json");
  if (!validate) {
    throw new Error("canonical-report-dataset.schema.json was not registered");
  }
  return { ajv, validate };
}

function countBy(rows, value) {
  const counts = new Map();
  for (const row of rows) {
    const key = value(row);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()].sort((left, right) =>
    String(left[0]).localeCompare(String(right[0])),
  );
}

function priceProblems(product, role, relationshipId) {
  const price = product?.price ?? {};
  return [
    price.reporting_price <= 0
      ? `${relationshipId}: ${role} reporting price is not positive`
      : null,
    price.regular_price === 0
      ? `${relationshipId}: ${role} regular_price is a zero sentinel`
      : null,
    price.discounted_price === 0
      ? `${relationshipId}: ${role} discounted_price is a zero sentinel`
      : null,
  ].filter(Boolean);
}

function distributionProblems(product, role, relationshipId) {
  const distribution = product?.distribution ?? {};
  return [
    typeof distribution.physical_store_distribution_count !== "number"
      ? `${relationshipId}: ${role} physical distribution is missing`
      : null,
    distribution.physical_store_distribution_count < 0
      ? `${relationshipId}: ${role} physical distribution is negative`
      : null,
    typeof distribution.service_area_presence_count !== "number"
      ? `${relationshipId}: ${role} service-area presence is missing`
      : null,
    distribution.service_area_presence_count < 0
      ? `${relationshipId}: ${role} service-area presence is negative`
      : null,
  ].filter(Boolean);
}

function auditDataset(dataset) {
  const relationships = dataset.product_relationships ?? [];
  const excluded = dataset.excluded_relationships ?? [];
  const blockers = [];
  const warnings = [];
  const outcomeCounts = Object.fromEntries(
    countBy(relationships, (row) => row.comparison.outcome),
  );
  const brandTypeCounts = Object.fromEntries(
    countBy(relationships, (row) => row.benchmark_product.brand_type),
  );
  const excludedReasonCounts = Object.fromEntries(
    countBy(excluded, (row) => row.reason_code),
  );

  const expectedSummary = {
    relationship_count: relationships.length,
    walmart_win_count: outcomeCounts.walmart_wins ?? 0,
    competitor_win_count: outcomeCounts.competitor_wins ?? 0,
    parity_count: outcomeCounts.parity ?? 0,
    unscored_count: outcomeCounts.unscored ?? 0,
    excluded_relationship_count: excluded.length,
  };
  for (const [key, expected] of Object.entries(expectedSummary)) {
    if (dataset.summary?.[key] !== expected) {
      blockers.push(
        `summary.${key} is ${dataset.summary?.[key]}, expected ${expected}`,
      );
    }
  }

  const relationshipIds = new Set();
  for (const relationship of relationships) {
    if (relationshipIds.has(relationship.relationship_id)) {
      blockers.push(
        `duplicate relationship_id ${relationship.relationship_id}`,
      );
    }
    relationshipIds.add(relationship.relationship_id);
    if (
      typeof relationship.benchmark_product.retailer_product_id !== "string" ||
      typeof relationship.competitor_product.retailer_product_id !== "string"
    ) {
      blockers.push(
        `${relationship.relationship_id}: product IDs must be strings`,
      );
    }
    if (
      relationship.benchmark_product.seller_status !== "qualified" &&
      relationship.benchmark_product.seller_status !== "not_applicable"
    ) {
      blockers.push(
        `${relationship.relationship_id}: Walmart benchmark seller is not qualified`,
      );
    }
    if (
      relationship.comparison.outcome === "walmart_wins" &&
      relationship.comparison.price_delta > 0
    ) {
      blockers.push(
        `${relationship.relationship_id}: outcome is walmart_wins but price_delta says Walmart is higher`,
      );
    }
    if (
      relationship.comparison.outcome === "competitor_wins" &&
      relationship.comparison.price_delta < 0
    ) {
      blockers.push(
        `${relationship.relationship_id}: outcome is competitor_wins but price_delta says Walmart is lower`,
      );
    }
    const expectedDelta =
      relationship.benchmark_product.price.reporting_price -
      relationship.competitor_product.price.reporting_price;
    if (
      Math.abs(relationship.comparison.price_delta - expectedDelta) > 0.0001
    ) {
      warnings.push(
        `${relationship.relationship_id}: price_delta does not reconcile to displayed reporting prices`,
      );
    }
    blockers.push(
      ...priceProblems(
        relationship.benchmark_product,
        "benchmark",
        relationship.relationship_id,
      ),
      ...priceProblems(
        relationship.competitor_product,
        "competitor",
        relationship.relationship_id,
      ),
      ...distributionProblems(
        relationship.benchmark_product,
        "benchmark",
        relationship.relationship_id,
      ),
      ...distributionProblems(
        relationship.competitor_product,
        "competitor",
        relationship.relationship_id,
      ),
    );
    if (
      !relationship.benchmark_product.image_url ||
      !relationship.competitor_product.image_url
    ) {
      warnings.push(
        `${relationship.relationship_id}: one or both product images missing`,
      );
    }
  }

  if (dataset.contracts?.distribution?.inventory_claim !== false) {
    blockers.push("distribution contract must not make an inventory claim");
  }
  if (dataset.contracts?.distribution?.stock_status_used !== false) {
    blockers.push("distribution contract must not use stock status");
  }
  if (dataset.contracts?.distribution?.sponsorship_used !== false) {
    blockers.push("distribution contract must not use sponsorship status");
  }
  if (dataset.contracts?.distribution?.extrapolation !== false) {
    blockers.push("distribution contract must not extrapolate store counts");
  }
  if (
    dataset.contracts?.service_area_presence?.presented_as_store_count !== false
  ) {
    blockers.push("service-area presence must not be presented as store count");
  }

  const topLosses = relationships
    .filter((row) => row.comparison.outcome === "competitor_wins")
    .sort(
      (left, right) =>
        right.benchmark_product.distribution.physical_store_distribution_count -
          left.benchmark_product.distribution
            .physical_store_distribution_count ||
        left.benchmark_product.title.localeCompare(
          right.benchmark_product.title,
        ),
    )
    .slice(0, 10);
  const topWins = relationships
    .filter((row) => row.comparison.outcome === "walmart_wins")
    .sort(
      (left, right) =>
        right.benchmark_product.distribution.physical_store_distribution_count -
          left.benchmark_product.distribution
            .physical_store_distribution_count ||
        left.benchmark_product.title.localeCompare(
          right.benchmark_product.title,
        ),
    )
    .slice(0, 10);

  return {
    blockers,
    warnings,
    expectedSummary,
    outcomeCounts,
    brandTypeCounts,
    excludedReasonCounts,
    topLosses,
    topWins,
  };
}

function table(rows) {
  if (!rows.length) return "_None._";
  return [
    "| Walmart product | Competitor product | Outcome | Walmart price | Competitor price | Walmart distribution | Gap |",
    "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ...rows.map(
      (row) =>
        `| ${[
          row.benchmark_product.title,
          `${row.competitor_product.title} (${row.competitor_product.retailer_id})`,
          row.comparison.outcome,
          row.benchmark_product.price.reporting_price_label,
          row.competitor_product.price.reporting_price_label,
          row.benchmark_product.distribution.physical_store_distribution_count.toLocaleString(),
          row.comparison.price_delta.toLocaleString("en-US", {
            maximumFractionDigits: 4,
          }),
        ]
          .map((cell) => String(cell).replaceAll("|", "\\|"))
          .join(" | ")} |`,
    ),
  ].join("\n");
}

function countsList(counts) {
  const rows = Object.entries(counts);
  return rows.length
    ? rows.map(([key, value]) => `- ${key}: ${value}`).join("\n")
    : "- None";
}

function markdown(input, dataset, audit) {
  const assessment = audit.blockers.length
    ? "Needs revision"
    : "Ready for preview QA";
  return `# Canonical Report Dataset Audit

Input: \`${input}\`

Assessment: **${assessment}**

## Dataset

- Analysis: \`${dataset.analysis_id}\`
- Product Pack: ${dataset.product_pack.name} \`${dataset.product_pack.id}\` v${dataset.product_pack.version}
- Generated: ${dataset.generated_at}
- Evidence observed: ${dataset.evidence_observed_at}
- Readiness: ${dataset.readiness.status}

## Summary reconciliation

- Included relationships: ${audit.expectedSummary.relationship_count}
- Walmart wins: ${audit.expectedSummary.walmart_win_count}
- Walmart losses: ${audit.expectedSummary.competitor_win_count}
- Parity: ${audit.expectedSummary.parity_count}
- Unscored: ${audit.expectedSummary.unscored_count}
- Excluded relationships: ${audit.expectedSummary.excluded_relationship_count}

## Brand type mix

${countsList(audit.brandTypeCounts)}

## Exclusion reasons

${countsList(audit.excludedReasonCounts)}

## Top Walmart losses by Walmart product footprint

${table(audit.topLosses)}

## Top Walmart wins by Walmart product footprint

${table(audit.topWins)}

## Blockers

${
  audit.blockers.length
    ? audit.blockers.map((item) => `- ${item}`).join("\n")
    : "- None"
}

## Warnings

${
  audit.warnings.length
    ? audit.warnings.map((item) => `- ${item}`).join("\n")
    : "- None"
}

## Guardrails checked

- Reportable prices are positive.
- Optional regular/discounted zero sentinels are not treated as valid prices.
- Retailer product IDs remain strings.
- Walmart benchmark seller status is qualified or not applicable.
- Benchmark and competitor products both carry distribution evidence.
- Store distribution does not make inventory, stock-status, sponsorship, or extrapolation claims.
- Service-area presence is not presented as store count.
`;
}

async function main() {
  const input = argument("--input");
  const output = argument("--output");
  if (
    !input ||
    process.argv.includes("--help") ||
    process.argv.includes("-h")
  ) {
    console.error(usage());
    return input ? 0 : 2;
  }

  const dataset = await loadJson(input);
  const { ajv, validate } = await contractValidator();
  if (!validate(dataset)) {
    console.error(
      ajv.errorsText(validate.errors, {
        separator: "\n",
      }),
    );
    return 1;
  }

  const audit = auditDataset(dataset);
  const report = markdown(input, dataset, audit);
  if (output) {
    const outputPath = isAbsolute(output)
      ? output
      : join(repositoryRoot, output);
    await mkdir(dirname(outputPath), { recursive: true });
    await writeFile(outputPath, report, "utf8");
    console.log(outputPath);
  } else {
    console.log(report);
  }
  return audit.blockers.length ? 1 : 0;
}

try {
  process.exitCode = await main();
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
