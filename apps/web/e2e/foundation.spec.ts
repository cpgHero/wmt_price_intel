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
  expect(html).toContain("theme-init");
  expect(html).toContain("rci-theme");
  expect(html).toContain("Toggle light and dark theme");
});
