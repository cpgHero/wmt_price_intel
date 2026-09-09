import { expect, test } from "@playwright/test";

const snapshot = {
  schema_version: "1.0.0-system-operations",
  generated_at: "2026-08-29T15:00:00Z",
  overall_state: "attention",
  release: {
    app_version: "0.1.0",
    commit_sha: "1234567890abcdef1234567890abcdef12345678",
    deployment_id: "deployment-1",
    environment: "production",
    service: "api",
    database_migration: "0053_scope_projections",
    expected_migration_heads: ["0053_scope_projections"],
    migration_matches: true,
    product_packs: [
      { id: "fresh_shell_eggs", version: "1.3.1", checksum: "a".repeat(64) },
    ],
    retailer_packs: [
      { id: "walmart_us", version: "1.0.0", checksum: "b".repeat(64) },
    ],
  },
  queues: [
    {
      label: "Search collection",
      state: "healthy",
      queued: 2,
      running: 1,
      expired_leases: 0,
      active_blocked: 0,
      failures_24h: 0,
    },
    {
      label: "Analysis",
      state: "healthy",
      queued: 0,
      running: 0,
      expired_leases: 0,
      active_blocked: 0,
      failures_24h: 0,
    },
    {
      label: "PDP enrichment",
      state: "healthy",
      queued: 0,
      running: 0,
      expired_leases: 0,
      active_blocked: 0,
      failures_24h: 0,
    },
    {
      label: "Matching AI review",
      state: "healthy",
      queued: 0,
      running: 0,
      expired_leases: 0,
      active_blocked: 0,
      failures_24h: 0,
    },
    {
      label: "Report materialization",
      state: "attention",
      queued: 0,
      running: 0,
      expired_leases: 0,
      active_blocked: 5,
      failures_24h: 0,
    },
  ],
  recent_analysis_failures: [
    {
      run_id: "8b2c4f5a-4b5a-4d70-9e61-7f4e7aaec245",
      product_pack_id: "fresh_shell_eggs",
      product_pack_version: "1.3.1",
      attempt_count: 3,
      max_attempts: 3,
      last_error: "ValueError: competitor price evidence was not reported",
      created_at: "2026-08-29T11:50:00Z",
      started_at: "2026-08-29T11:51:00Z",
      completed_at: "2026-08-29T12:00:00Z",
    },
  ],
  recent_report_materialization_failures: [
    {
      job_id: "14dc2a17-01d7-486f-9aab-f328b3e10157",
      analysis_id: "fresh_strawberries-analysis-f8ecc77a",
      product_pack_id: "fresh_strawberries",
      product_pack_version: "1.4.0",
      status: "blocked",
      stage: "blocked",
      progress_current: 6,
      progress_total: null,
      attempt_count: 3,
      max_attempts: 3,
      last_error: "materialization API 500: Internal Server Error",
      created_at: "2026-08-29T12:50:00Z",
      started_at: "2026-08-29T12:51:00Z",
      completed_at: null,
      updated_at: "2026-08-29T13:00:00Z",
    },
  ],
  publication: {
    active_ready_reports: 6,
    active_pending_reports: 0,
    active_blocked_reports: 0,
    open_validation_blockers: 0,
    latest_ready_report_at: "2026-08-29T14:00:00Z",
    latest_successful_collection_at: "2026-08-29T13:00:00Z",
  },
  provider: {
    active_cooldowns: 0,
    last_429_at: null,
    global_rps: 2,
    global_rpm: 108,
    maximum_attempts: 5,
  },
  spend_30d: {
    search_credits: 120,
    pdp_credits: 30,
    metricscart_estimated_usd: 0.3,
    ai_estimated_usd: 1.25,
    ai_completed_tasks_without_cost: 1,
    provider_billing_is_authoritative: true,
  },
  controls: {
    collection_provider: null,
    product_detail_enrichment_enabled: true,
    analysis_pipeline_enabled: true,
    matching_ai_review_enabled: true,
    ai_enabled: true,
    openai_matching_max_request_cost_usd: 0.35,
  },
  recovery: {
    database_backup: {
      status: "not_recorded",
      verified_at: null,
      maximum_age_hours: 24,
    },
    restore_drill: {
      status: "not_recorded",
      verified_at: null,
      maximum_age_days: 90,
    },
    evidence_source: "operator-attested Railway environment timestamps",
  },
};

test("protects System Operations", async ({ page }) => {
  await page.route("**/api/admin/session", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ configured: true, authenticated: false }),
    }),
  );
  await page.goto("/admin/operations");
  await expect(
    page.getByRole("heading", {
      name: "Administrator authentication required",
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Open System Operations" }),
  ).toBeVisible();
});

test("renders safe recent analysis failure details", async ({ page }) => {
  await page.route("**/api/admin/session", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ configured: true, authenticated: true }),
    }),
  );
  await page.route("**/api/admin/operations", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(snapshot),
    }),
  );
  await page.goto("/admin/operations");

  await expect(
    page.getByRole("heading", { name: "Recent analysis failures" }),
  ).toBeVisible();
  await expect(
    page.getByText("fresh_shell_eggs", { exact: true }).last(),
  ).toBeVisible();
  await expect(page.getByText("v1.3.1")).toBeVisible();
  await expect(
    page.getByText("8b2c4f5a-4b5a-4d70-9e61-7f4e7aaec245"),
  ).toBeVisible();
  await expect(page.getByText("3 / 3")).toBeVisible();
  await expect(
    page.getByText("ValueError: competitor price evidence was not reported"),
  ).toBeVisible();
});

test("renders recent report materialization failure details", async ({
  page,
}) => {
  await page.route("**/api/admin/session", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ configured: true, authenticated: true }),
    }),
  );
  await page.route("**/api/admin/operations", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(snapshot),
    }),
  );
  await page.goto("/admin/operations");

  await expect(
    page.getByRole("heading", {
      name: "Recent report materialization failures",
    }),
  ).toBeVisible();
  await expect(
    page.getByText("fresh_strawberries", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("fresh_strawberries-analysis-f8ecc77a"),
  ).toBeVisible();
  await expect(
    page.getByText("Job 14dc2a17-01d7-486f-9aab-f328b3e10157"),
  ).toBeVisible();
  await expect(page.getByText("6 / —")).toBeVisible();
  await expect(page.getByText("3 / 3").last()).toBeVisible();
  await expect(
    page.getByText("materialization API 500: Internal Server Error"),
  ).toBeVisible();
});

test("renders live release, queue, spend, and recovery state", async ({
  page,
}) => {
  await page.route("**/api/admin/session", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ configured: true, authenticated: true }),
    }),
  );
  await page.route("**/api/admin/operations", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(snapshot),
    }),
  );
  await page.goto("/admin/operations");
  await expect(
    page.getByRole("heading", { name: "Operational follow-up is required" }),
  ).toBeVisible();
  await expect(page.getByText("1234567890ab")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Queue health" }),
  ).toBeVisible();
  await expect(page.getByText("$0.30")).toBeVisible();
  await expect(page.getByText("Not exposed to API")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Backup and restore readiness" }),
  ).toBeVisible();
  await expect(
    page.getByText("not recorded", { exact: true }).first(),
  ).toBeVisible();
});
