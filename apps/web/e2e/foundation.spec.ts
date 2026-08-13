import { expect, test } from "@playwright/test";

test("serves the application shell, workflow routes, and health route", async ({
  request,
}) => {
  const home = await request.get("/");
  expect(home.ok()).toBe(true);
  const homeHtml = await home.text();
  expect(homeHtml).toContain("Your competitive intelligence workspace.");
  expect(homeHtml).toContain("Schedules &amp; Alerts");
  expect(homeHtml).toContain("Data Quality");

  const collections = await request.get("/collections");
  expect(collections.ok()).toBe(true);
  const collectionsHtml = await collections.text();
  expect(collectionsHtml).toContain("New collection");
  expect(collectionsHtml).toContain("Open collection builder");

  const builder = await request.get("/collections/new");
  expect(builder.ok()).toBe(true);
  expect(await builder.text()).toContain(
    "Collection options could not be loaded",
  );

  const automation = await request.get("/automation");
  expect(automation.ok()).toBe(true);
  expect(await automation.text()).toContain("Schedules &amp; Alerts");

  const reports = await request.get("/analyses");
  expect(reports.ok()).toBe(true);
  expect(await reports.text()).toContain("Competitive intelligence library");

  const matchWorkbench = await request.get("/workspace/matches");
  expect(matchWorkbench.ok()).toBe(true);
  expect(await matchWorkbench.text()).toContain("Match Workbench");

  const brandWorkbench = await request.get("/workspace/brands");
  expect(brandWorkbench.ok()).toBe(true);
  expect(await brandWorkbench.text()).toContain("Brand Workbench");

  const quality = await request.get("/data-quality");
  expect(quality.ok()).toBe(true);
  expect(await quality.text()).toContain("Decision readiness");

  const productPacks = await request.get("/admin/product-packs");
  expect(productPacks.ok()).toBe(true);
  const productPacksHtml = await productPacks.text();
  expect(productPacksHtml).toContain("Product Packs");
  expect(productPacksHtml).toContain("Governed administration");

  const response = await request.get("/health");
  expect(response.ok()).toBe(true);
  await expect(response.json()).resolves.toMatchObject({
    status: "ok",
    service: "web",
  });
});

test("serves the branded shell and no-flash theme controls", async ({
  request,
}) => {
  const response = await request.get("/");
  const html = await response.text();

  expect(response.ok()).toBe(true);
  expect(html).toContain("CPGHero");
  expect(html).toContain("Application navigation");
  expect(html).toContain("Home");
  expect(html).toContain("Match Workbench");
  expect(html).toContain("Brand Workbench");
  expect(html).toContain("Competitive Intelligence");
  expect(html).toContain("Study Discovery");
  expect(html).not.toContain("Price Intelligence (Coming soon)");
  expect(html).toContain("theme-init");
  expect(html).toContain("rci-theme");
  expect(html).toContain("Toggle light and dark theme");
});

test("supports the responsive application navigation", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");

  const sidebar = page.getByLabel("Application sidebar");
  await expect(sidebar).toBeVisible();
  await expect(
    sidebar.getByRole("button", { name: "Collapse sidebar" }),
  ).toBeEnabled();
  await expect(
    sidebar.getByRole("link", { name: "Home", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await expect(
    sidebar.getByRole("link", { name: "Match Workbench" }),
  ).toBeVisible();

  const operationsGroup = sidebar.getByRole("button", { name: "Operations" });
  await expect(operationsGroup).toHaveAttribute("aria-expanded", "false");
  await operationsGroup.click();
  await expect(operationsGroup).toHaveAttribute("aria-expanded", "true");
  await sidebar.getByRole("link", { name: "Collections" }).click();
  await expect(page).toHaveURL(/\/collections$/);
  await expect(
    sidebar.getByRole("link", { name: "Collections" }),
  ).toHaveAttribute("aria-current", "page");

  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await expect(
    page.getByRole("button", { name: "Expand sidebar" }),
  ).toBeVisible();
  await sidebar.getByRole("button", { name: "Operations" }).hover();
  const operationsFlyout = page.getByLabel("Operations navigation");
  await expect(operationsFlyout).toBeVisible();
  await expect(
    operationsFlyout.getByRole("link", { name: /Schedules & Alerts/ }),
  ).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(sidebar).toBeHidden();
  const menuButton = page.getByRole("button", {
    name: "Open application navigation",
  });
  await menuButton.click();
  const mobileNavigation = page.getByRole("dialog", {
    name: "Mobile application navigation",
  });
  await expect(mobileNavigation).toBeVisible();
  await expect(
    mobileNavigation.getByText("Competitive Intelligence", { exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(mobileNavigation).toBeHidden();
  await expect(menuButton).toBeFocused();
});
