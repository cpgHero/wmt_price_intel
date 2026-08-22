import { expect, test } from "@playwright/test";

import { platformDocumentation } from "../src/lib/platform-docs";

test("protects the owner and administrator documentation", async ({ page }) => {
  await page.route("**/api/admin/session", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ configured: true, authenticated: false }),
    });
  });

  await page.goto("/admin/docs");
  await expect(
    page.getByRole("heading", {
      name: "Administrator authentication required",
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Open Platform Docs" }),
  ).toBeVisible();
});

test("searches and navigates maintained platform guides", async ({ page }) => {
  await page.route("**/api/admin/session", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ configured: true, authenticated: true }),
    });
  });
  await page.route("**/api/admin/docs", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(platformDocumentation),
    });
  });

  await page.goto("/admin/docs");
  await expect(
    page.getByRole("heading", { name: "Platform Owner & Administrator Guide" }),
  ).toBeVisible();
  await expect(page.getByText("17 maintained guides")).toBeVisible();

  await page
    .getByRole("button", { name: /Data lifecycle: collection to reporting/ })
    .click();
  await expect(
    page.getByRole("heading", { name: "Start-to-finish flow" }),
  ).toBeVisible();

  const search = page.getByRole("searchbox", {
    name: "Search all platform docs",
  });
  await search.fill("paired median gap");
  await expect(page.getByText("1 guide found")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Metric & evidence dictionary" }),
  ).toBeVisible();
  await expect(
    page.getByText("The median of competitor price minus benchmark price"),
  ).toBeVisible();
});
