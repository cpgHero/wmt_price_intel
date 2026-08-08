import { readFile, readdir } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(packageRoot, "../../..");
const ajv = new Ajv2020({
  allErrors: true,
  allowUnionTypes: true,
  strict: true,
});
addFormats(ajv);

async function loadJson(...parts) {
  return JSON.parse(await readFile(join(repositoryRoot, ...parts), "utf8"));
}

async function validator(schemaName) {
  return ajv.compile(await loadJson("schemas", schemaName));
}

async function assertValid(validate, document, label) {
  if (!validate(document)) {
    throw new Error(
      `${label}: ${ajv.errorsText(validate.errors, { separator: "\n" })}`,
    );
  }
}

const collectionValidator = await validator(
  "collection-definition.schema.json",
);
const analysisValidator = await validator("analysis-result.schema.json");
const alertValidator = await validator("alert-definition.schema.json");
const productPackValidator = await validator("product-pack.schema.json");
const benchmarkValidator = await validator("golden-benchmarks.schema.json");
const productDetailCatalogValidator = await validator(
  "product-detail-catalog.schema.json",
);

await assertValid(
  alertValidator,
  await loadJson("examples", "alert-definition.amazon-pressure.json"),
  "alert definition",
);
await assertValid(
  collectionValidator,
  await loadJson("examples", "collection-definition.strawberries.json"),
  "collection definition",
);
await assertValid(
  analysisValidator,
  await loadJson("examples", "analysis-result.strawberries.json"),
  "analysis result",
);
await assertValid(
  benchmarkValidator,
  await loadJson("fixtures", "golden", "benchmarks.json"),
  "golden benchmarks",
);
await assertValid(
  productDetailCatalogValidator,
  await loadJson("config", "product-detail-catalog.json"),
  "product detail catalog",
);

const productPackFiles = (await readdir(join(repositoryRoot, "product-packs")))
  .filter((name) => name.startsWith("fresh_") && name.endsWith(".json"))
  .sort();
for (const productPackFile of productPackFiles) {
  await assertValid(
    productPackValidator,
    await loadJson("product-packs", productPackFile),
    productPackFile,
  );
}

const profile = await loadJson(
  "fixtures",
  "location_master",
  "locations.profile.json",
);
if (profile.rows !== 157806) {
  throw new Error(
    `location profile: expected 157806 rows, found ${profile.rows}`,
  );
}

console.log(
  `Validated ${productPackFiles.length + 5} normative JSON documents.`,
);
