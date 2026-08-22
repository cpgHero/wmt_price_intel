import { expect, test } from "@playwright/test";

test("shows durable report progress and trust audit evidence", async ({
  page,
}) => {
  await page.route("**/api/admin/session", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ configured: true, authenticated: true }),
    });
  });
  await page.route("**/api/admin/report-publishing", async (route) => {
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

  await page.goto("/admin/report-publishing");
  await expect(
    page.getByRole("heading", { name: "Report Publishing" }),
  ).toBeVisible();
  await expect(
    page.getByText("fresh_fluid_milk-release-candidate"),
  ).toBeVisible();
  await expect(page.getByText("7 of 13")).toBeVisible();
  await page.getByText("Trust audit · passed").click();
  await expect(page.getByText("0 blocking errors")).toBeVisible();
  await expect(page.getByText("6 competitive views")).toBeVisible();
});
