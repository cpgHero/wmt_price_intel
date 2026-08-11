import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(packageRoot, "../../..");
const outputDirectory = join(packageRoot, "src/generated");
const contracts = [
  ["alert-definition.schema.json", "alert-definition.ts"],
  ["agent-output.schema.json", "agent-output.ts"],
  ["agent-prompt.schema.json", "agent-prompt.ts"],
  ["analysis-evidence.schema.json", "analysis-evidence.ts"],
  ["analysis-brief.schema.json", "analysis-brief.ts"],
  ["analysis-result.schema.json", "analysis-result.ts"],
  ["analysis-result-v2.schema.json", "analysis-result-v2.ts"],
  ["canonical-product.schema.json", "canonical-product.ts"],
  ["collection-definition.schema.json", "collection-definition.ts"],
  [
    "collection-geography-request.schema.json",
    "collection-geography-request.ts",
  ],
  [
    "collection-geography-resolution.schema.json",
    "collection-geography-resolution.ts",
  ],
  ["collection-scope-estimate.schema.json", "collection-scope-estimate.ts"],
  ["golden-benchmarks.schema.json", "golden-benchmarks.ts"],
  ["historical-input-manifest.schema.json", "historical-input-manifest.ts"],
  ["normalized-offer.schema.json", "normalized-offer.ts"],
  ["narrative-benchmarks.schema.json", "narrative-benchmarks.ts"],
  ["product-detail-catalog.schema.json", "product-detail-catalog.ts"],
  ["product-detail-snapshot.schema.json", "product-detail-snapshot.ts"],
  ["product-match-decision.schema.json", "product-match-decision.ts"],
  ["product-match-review.schema.json", "product-match-review.ts"],
  ["product-pack.schema.json", "product-pack.ts"],
  ["provider-error.schema.json", "provider-error.ts"],
  ["report-blueprint.schema.json", "report-blueprint.ts"],
  ["report-view.schema.json", "report-view.ts"],
];

await mkdir(outputDirectory, { recursive: true });
for (const [schemaName, outputName] of contracts) {
  const schemaPath = join(repositoryRoot, "schemas", schemaName);
  const schema = JSON.parse(await readFile(schemaPath, "utf8"));
  const source = await compile(schema, schema.title, {
    cwd: dirname(schemaPath),
    bannerComment:
      "/* Generated from the normative JSON Schema. Do not edit manually. */",
    style: { singleQuote: false },
  });
  await writeFile(join(outputDirectory, outputName), source, "utf8");
}
