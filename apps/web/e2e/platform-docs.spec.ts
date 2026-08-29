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
  await expect(page.getByText("20 maintained guides")).toBeVisible();

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
  await expect(page.getByText("2 guides found")).toBeVisible();
  await page
    .getByRole("button", { name: /Metric & evidence dictionary/ })
    .click();
  await expect(
    page.getByRole("heading", { name: "Metric & evidence dictionary" }),
  ).toBeVisible();
  await expect(
    page.getByText("The median of competitor price minus benchmark price"),
  ).toBeVisible();

  await search.fill("AI integration & operating boundaries");
  await expect(page.getByText("1 guide found")).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "AI integration & operating boundaries",
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Current production AI inventory" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Human decision boundary" }),
  ).toBeVisible();

  await search.fill("Retailer integration registry");
  await expect(page.getByText("1 guide found")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Enabled Search-by-ZIP adapters" }),
  ).toBeVisible();

  await search.fill("Source-to-metric lineage");
  await expect(page.getByText("1 guide found")).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "The four grains administrators must distinguish",
    }),
  ).toBeVisible();
});
