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

const schemaNames = (await readdir(join(repositoryRoot, "schemas")))
  .filter((name) => name.endsWith(".json"))
  .sort();
for (const schemaName of schemaNames) {
  ajv.addSchema(await loadJson("schemas", schemaName), schemaName);
}

function validator(schemaName) {
  const validate = ajv.getSchema(schemaName);
  if (!validate) throw new Error(`Schema was not registered: ${schemaName}`);
  return validate;
}

async function assertValid(validate, document, label) {
  if (!validate(document)) {
    throw new Error(
      `${label}: ${ajv.errorsText(validate.errors, { separator: "\n" })}`,
    );
  }
}

const collectionValidator = validator("collection-definition.schema.json");
const geographyRequestValidator = validator(
  "collection-geography-request.schema.json",
);
const geographyResolutionValidator = validator(
  "collection-geography-resolution.schema.json",
);
const scopeEstimateValidator = validator(
  "collection-scope-estimate.schema.json",
);
const analysisValidator = validator("analysis-result.schema.json");
const analysisV2Validator = validator("analysis-result-v2.schema.json");
const analysisEvidenceValidator = validator("analysis-evidence.schema.json");
const analysisBriefValidator = validator("analysis-brief.schema.json");
const canonicalProductValidator = validator("canonical-product.schema.json");
const productDetailSnapshotValidator = validator(
  "product-detail-snapshot.schema.json",
);
const agentOutputValidator = validator("agent-output.schema.json");
const agentPromptValidator = validator("agent-prompt.schema.json");
const reportBlueprintValidator = validator("report-blueprint.schema.json");
const reportViewValidator = validator("report-view.schema.json");
const productMatchReviewValidator = validator(
  "product-match-review.schema.json",
);
const productMatchScopeValidator = validator("product-match-scope.schema.json");
const productFootprintValidator = validator("product-footprint.schema.json");
const scopedMatchAssignmentValidator = validator(
  "scoped-match-assignment.schema.json",
);
const brandClassificationDecisionValidator = validator(
  "brand-classification-decision.schema.json",
);
const brandWorkbenchValidator = validator("brand-workbench.schema.json");
const brandDiscoveryValidator = validator(
  "brand-discovery-record.schema.json",
);
const brandFoundationValidator = validator("brand-foundation.schema.json");
const retailerPackValidator = validator("retailer-pack.schema.json");
const historicalInputManifestValidator = validator(
  "historical-input-manifest.schema.json",
);
const alertValidator = validator("alert-definition.schema.json");
const productPackValidator = validator("product-pack.schema.json");
const productPackCapabilitiesValidator = validator(
  "product-pack-capabilities.schema.json",
);
const productPackDraftValidator = validator("product-pack-draft.schema.json");
const benchmarkValidator = validator("golden-benchmarks.schema.json");
const narrativeBenchmarkValidator = validator(
  "narrative-benchmarks.schema.json",
);
const productDetailCatalogValidator = validator(
  "product-detail-catalog.schema.json",
);

await assertValid(
  geographyRequestValidator,
  {
    primary_retailer_id: "walmart_us",
    competitor_retailer_ids: ["aldi_us"],
    country: "USA",
    primary_selection: { mode: "custom_zips", zipcodes: ["03038"] },
    competitor_correspondence: { mode: "same_zip" },
  },
  "collection geography request",
);
await assertValid(
  geographyResolutionValidator,
  {
    id: "00000000-0000-0000-0000-000000000201",
    request: {
      primary_retailer_id: "walmart_us",
      competitor_retailer_ids: ["aldi_us"],
      country: "USA",
      primary_selection: { mode: "custom_zips", zipcodes: ["03038"] },
      competitor_correspondence: { mode: "same_zip" },
    },
    checksum: "a".repeat(64),
    status: "ready",
    counts: { total: 0, primary: 0, competitors: { aldi_us: 0 } },
    locations: [],
    edges: [],
    created_at: "2026-08-11T00:00:00Z",
  },
  "collection geography resolution",
);
await assertValid(
  scopeEstimateValidator,
  {
    id: "00000000-0000-0000-0000-000000000202",
    definition_id: "collection-test",
    resolution_id: "00000000-0000-0000-0000-000000000201",
    configuration_checksum: "b".repeat(64),
    geography_checksum: "a".repeat(64),
    retailers: [
      {
        retailer_id: "walmart_us",
        location_units: 2,
        credits_per_page: 1,
        max_pages: 5,
        estimated_pages: 10,
        estimated_credits: 10,
      },
    ],
    estimated_total_pages: 10,
    estimated_total_credits: 10,
    expires_at: "2026-08-11T00:30:00Z",
    created_at: "2026-08-11T00:00:00Z",
  },
  "collection scope estimate",
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
  analysisBriefValidator,
  await loadJson("examples", "analysis-brief.ground-beef.json"),
  "analysis brief",
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
await assertValid(
  reportViewValidator,
  await loadJson("examples", "report-view.ground-beef.json"),
  "report view",
);
await assertValid(
  productMatchReviewValidator,
  await loadJson("examples", "product-match-review.ground-beef.json"),
  "product match review",
);
const exampleScope = {
  mode: "observed_benchmark_product_footprint",
  relationship_role: "primary",
  comparison_family_key: "whole_milk_gallon",
  definition: {
    source_analysis_id: "analysis-milk",
    benchmark_location_scope_keys: ["walmart_us|03038|1753"],
    excluded_benchmark_location_scope_keys: [],
    future_location_policy: "review",
  },
  checksum: "c".repeat(64),
  artifact_id: null,
};
await assertValid(
  productMatchScopeValidator,
  exampleScope,
  "product match scope",
);
await assertValid(
  productFootprintValidator,
  {
    schema_version: "1.0.0",
    analysis_id: "analysis-milk",
    retailer_id: "walmart_us",
    product_id: "15136790",
    source_authority: "search",
    locations: [
      {
        scope_key: "walmart_us|03038|1753",
        store_number: "1753",
        zipcode: "03038",
        observations: 1,
        lowest_positive_price: 3.98,
      },
    ],
    checksum: "d".repeat(64),
  },
  "product footprint",
);
await assertValid(
  scopedMatchAssignmentValidator,
  {
    schema_version: "1.0.0",
    assignment_id: "assignment-milk-1",
    analysis_id: "analysis-milk",
    match_revision_id: "00000000-0000-0000-0000-000000000301",
    brand_revision_id: null,
    competitor_retailer_id: "aldi_us",
    relationship_id: "00000000-0000-0000-0000-000000000302",
    profile_id: "private_label_exact",
    comparison_family_key: "whole_milk_gallon",
    relationship_role: "primary",
    benchmark_product_id: "15136790",
    competitor_product_id: "aldi-whole-milk-gallon",
    benchmark_location_scope_key: "walmart_us|03038|1753",
    status: "active",
    source_authority: "search",
    benchmark_value: 3.98,
    competitor_value: 3.89,
    comparison_metric: "package_price",
    winner: "competitor_lower",
  },
  "scoped match assignment",
);
await assertValid(
  brandClassificationDecisionValidator,
  {
    expected_revision: 0,
    retailer_id: "walmart_us",
    normalized_brand: "great value",
    role: "private_label",
    decision: "confirmed",
    reason: "Retailer-owned portfolio",
  },
  "brand classification decision",
);
await assertValid(
  brandWorkbenchValidator,
  {
    schema_version: "1.0.0",
    analysis_id: "analysis-milk",
    product_pack_id: "fresh_fluid_milk",
    product_pack_version: "1.2.0",
    revision: 0,
    future_application: null,
    retailers: [{ id: "walmart_us", name: "Walmart" }],
    brands: [
      {
        retailer_id: "walmart_us",
        normalized_brand: "great value",
        display_brand: "Great Value",
        role: "private_label",
        status: "suggested",
        origin: "product_pack",
        observed_products: 1,
        observed_locations: 1,
        observed_zipcodes: 1,
        location_share: 1,
        distribution_tier: "single_location",
        distribution_evidence: "search_brand_field",
        product_examples: [],
      },
    ],
    summary: {
      confirmed: 0,
      suggested: 1,
      unclassified: 0,
      rejected: 0,
    },
  },
  "brand workbench",
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
  narrativeBenchmarkValidator,
  await loadJson("fixtures", "golden", "narrative-benchmarks.json"),
  "narrative benchmarks",
);
await assertValid(
  productDetailCatalogValidator,
  await loadJson("config", "product-detail-catalog.json"),
  "product detail catalog",
);
await assertValid(
  productPackCapabilitiesValidator,
  await loadJson("config", "product-pack-capabilities.json"),
  "Product Pack capabilities",
);
await assertValid(
  productPackDraftValidator,
  await loadJson("examples", "product-pack-draft.ground-beef.json"),
  "Product Pack draft",
);
await assertValid(
  brandDiscoveryValidator,
  await loadJson("examples", "brand-discovery-record.example.json"),
  "brand discovery record",
);

const brandFoundationIndex = await loadJson("brand-foundations", "index.json");
for (const foundation of brandFoundationIndex.foundations) {
  await assertValid(
    brandFoundationValidator,
    await loadJson("brand-foundations", ...foundation.file.split("/")),
    foundation.file,
  );
}

const retailerPackIndex = await loadJson("retailer-packs", "index.json");
for (const retailerPack of retailerPackIndex.packs) {
  await assertValid(
    retailerPackValidator,
    await loadJson("retailer-packs", ...retailerPack.file.split("/")),
    retailerPack.file,
  );
}

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
    brandFoundationIndex.foundations.length +
    retailerPackIndex.packs.length +
    12
  } normative JSON documents.`,
);
