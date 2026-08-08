import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(packageRoot, "../../..");
const outputDirectory = join(packageRoot, "src/generated");
const contracts = [
  ["alert-definition.schema.json", "alert-definition.ts"],
  ["analysis-result.schema.json", "analysis-result.ts"],
  ["collection-definition.schema.json", "collection-definition.ts"],
  ["golden-benchmarks.schema.json", "golden-benchmarks.ts"],
  ["normalized-offer.schema.json", "normalized-offer.ts"],
  ["product-detail-catalog.schema.json", "product-detail-catalog.ts"],
  ["product-pack.schema.json", "product-pack.ts"],
  ["provider-error.schema.json", "provider-error.ts"],
];

await mkdir(outputDirectory, { recursive: true });
for (const [schemaName, outputName] of contracts) {
  const schemaPath = join(repositoryRoot, "schemas", schemaName);
  const schema = JSON.parse(await readFile(schemaPath, "utf8"));
  const source = await compile(schema, schema.title, {
    bannerComment:
      "/* Generated from the normative JSON Schema. Do not edit manually. */",
    style: { singleQuote: false },
  });
  await writeFile(join(outputDirectory, outputName), source, "utf8");
}
