import { expect, test } from "@playwright/test";

test("shows durable report progress and trust audit evidence", async ({
  page,
}) => {
  let customerAccessRequests = 0;
  await page.route("**/api/admin/session*", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ configured: true, authenticated: true }),
    });
  });
  await page.route(/\/api\/admin\/report-publishing(?:\?|$)/, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "job-1",
          analysis_id: "fresh_fluid_milk-release-candidate",
          reporting_status: "pending",
          product_pack_id: "fresh_fluid_milk",
          product_pack_version: "1.7.0",
          status: "running",
          stage: "competitive_portfolio:all_brand:3",
          progress_current: 7,
          progress_total: 13,
          attempt_count: 1,
          max_attempts: 3,
          last_error: null,
          audit_document: null,
          created_at: "2026-08-21T20:00:00Z",
          updated_at: "2026-08-21T20:05:00Z",
        },
        {
          id: "job-2",
          analysis_id: "fresh_shell_eggs-certified",
          reporting_status: "ready",
          product_pack_id: "fresh_shell_eggs",
          product_pack_version: "2.0.0",
          status: "succeeded",
          stage: "complete",
          progress_current: 10,
          progress_total: 10,
          attempt_count: 1,
          max_attempts: 3,
          last_error: null,
          audit_document: {
            status: "passed",
            error_count: 0,
            warning_count: 4,
            price_architecture_document_count: 3,
            competitive_portfolio_document_count: 6,
          },
          created_at: "2026-08-21T18:00:00Z",
          updated_at: "2026-08-21T18:15:00Z",
        },
      ]),
    });
  });
  await page.route("**/api/admin/report-publishing/summary", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        active_reports: {
          active_total: 5,
          active_ready: 5,
          active_pending: 0,
          active_blocked: 0,
          latest_ready_at: "2026-09-10T03:33:06.685Z",
        },
        recent_job_counts: {
          running: 1,
          succeeded: 1,
        },
        recent_jobs: [],
      }),
    });
  });
  await page.route(
    "**/api/admin/customer-report-access?limit=100",
    async (route) => {
      customerAccessRequests += 1;
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          schema_version: "1.0.0-admin-customer-report-access",
          grants: [
            {
              access_id: "grant-1",
              account_id: "account-1",
              account_slug: "ghretail",
              account_display_name: "GHRetail",
              workspace_id: null,
              workspace_slug: null,
              workspace_display_name: null,
              analysis_id: "fresh_shell_eggs-certified",
              analysis_result_id: "result-1",
              title: "Egg price intelligence",
              category: "Eggs",
              status: "active",
              granted_at: "2026-09-14T12:00:00Z",
            },
          ],
          grantable_reports: [
            {
              analysis_id: "fresh_shell_eggs-certified",
              analysis_result_id: "result-1",
              title: "Egg price intelligence",
              category: "Eggs",
              product_pack_id: "fresh_shell_eggs",
              product_pack_version: "2.0.0",
              created_at: "2026-09-14T10:00:00Z",
            },
          ],
        }),
      });
    },
  );

  await page.goto("/admin/report-publishing");
  await expect(
    page.getByRole("heading", { name: "Pipeline Status" }),
  ).toBeVisible();
  await expect(page.getByText("5 ready reports")).toBeVisible();
  await expect(page.getByText("0 pending · 0 blocked")).toBeVisible();
  await expect(
    page.getByText("fresh_fluid_milk-release-candidate"),
  ).toBeVisible();
  await expect(page.getByText("7 of 13")).toBeVisible();
  await page.getByText("Trust audit · passed").click();
  await expect(page.getByText("0 blocking errors")).toBeVisible();
  await expect(page.getByText("6 competitive views")).toBeVisible();
  await expect(
    page.getByText("Grant reports to customer accounts"),
  ).toHaveCount(0);
  await expect(
    page.locator("td strong").filter({ hasText: /^GHRetail$/ }),
  ).toHaveCount(0);
  expect(customerAccessRequests).toBe(0);
});
