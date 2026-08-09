import { expect, test } from "@playwright/test";

test("serves the application shell, workflow routes, and health route", async ({
  request,
}) => {
  const home = await request.get("/");
  expect(home.ok()).toBe(true);
  expect(await home.text()).toContain(
    "Know the shelf before the market moves.",
  );

  const collections = await request.get("/collections");
  expect(collections.ok()).toBe(true);
  const collectionsHtml = await collections.text();
  expect(collectionsHtml).toContain("New collection");
  expect(collectionsHtml).toContain("Product Packs unavailable");

  const automation = await request.get("/automation");
  expect(automation.ok()).toBe(true);
  expect(await automation.text()).toContain("Scheduled intelligence");

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
