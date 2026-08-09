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
const analysisV2Validator = await validator("analysis-result-v2.schema.json");
const analysisEvidenceValidator = await validator(
  "analysis-evidence.schema.json",
);
const canonicalProductValidator = await validator(
  "canonical-product.schema.json",
);
const productDetailSnapshotValidator = await validator(
  "product-detail-snapshot.schema.json",
);
const agentOutputValidator = await validator("agent-output.schema.json");
const agentPromptValidator = await validator("agent-prompt.schema.json");
const reportBlueprintValidator = await validator(
  "report-blueprint.schema.json",
);
const historicalInputManifestValidator = await validator(
  "historical-input-manifest.schema.json",
);
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
const exampleFiles = await readdir(join(repositoryRoot, "examples"));
const collectionDefinitionFiles = exampleFiles
  .filter(
    (name) =>
      name.startsWith("collection-definition.") && name.endsWith(".json"),
  )
  .sort();
for (const definitionFile of collectionDefinitionFiles) {
  await assertValid(
    collectionValidator,
    await loadJson("examples", definitionFile),
    definitionFile,
  );
}
const analysisResultFiles = exampleFiles
  .filter(
    (name) =>
      name.startsWith("analysis-result.") &&
      !name.startsWith("analysis-result-v2.") &&
      name.endsWith(".json"),
  )
  .sort();
for (const resultFile of analysisResultFiles) {
  await assertValid(
    analysisValidator,
    await loadJson("examples", resultFile),
    resultFile,
  );
}
await assertValid(
  analysisV2Validator,
  await loadJson("examples", "analysis-result-v2.ground-beef.json"),
  "AnalysisResult V2",
);
await assertValid(
  analysisEvidenceValidator,
  await loadJson("examples", "analysis-evidence.ground-beef.json"),
  "analysis evidence",
);
await assertValid(
  canonicalProductValidator,
  await loadJson("examples", "canonical-product.ground-beef.json"),
  "canonical product",
);
await assertValid(
  productDetailSnapshotValidator,
  await loadJson("examples", "product-detail-snapshot.aldi.json"),
  "product detail snapshot",
);
await assertValid(
  agentOutputValidator,
  await loadJson("examples", "agent-output.ground-beef-insight.json"),
  "governed agent output",
);
await assertValid(
  reportBlueprintValidator,
  await loadJson("examples", "report-blueprint.ground-beef.json"),
  "report blueprint",
);
const historicalInputManifestFiles = exampleFiles
  .filter(
    (name) =>
      name.startsWith("historical-input-manifest.") && name.endsWith(".json"),
  )
  .sort();
for (const manifestFile of historicalInputManifestFiles) {
  await assertValid(
    historicalInputManifestValidator,
    await loadJson("examples", manifestFile),
    manifestFile,
  );
}
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

const reportBlueprintFiles = (
  await readdir(join(repositoryRoot, "report-blueprints"))
)
  .filter((name) => name.endsWith(".json"))
  .sort();
for (const reportBlueprintFile of reportBlueprintFiles) {
  await assertValid(
    reportBlueprintValidator,
    await loadJson("report-blueprints", reportBlueprintFile),
    reportBlueprintFile,
  );
}

const agentPromptFiles = (await readdir(join(repositoryRoot, "agent-prompts")))
  .filter((name) => name.endsWith(".json"))
  .sort();
for (const agentPromptFile of agentPromptFiles) {
  await assertValid(
    agentPromptValidator,
    await loadJson("agent-prompts", agentPromptFile),
    agentPromptFile,
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
  `Validated ${
    productPackFiles.length +
    collectionDefinitionFiles.length +
    analysisResultFiles.length +
    historicalInputManifestFiles.length +
    reportBlueprintFiles.length +
    agentPromptFiles.length +
    9
  } normative JSON documents.`,
);
