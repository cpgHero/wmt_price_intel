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
  expect(collectionsHtml).toContain("Runs &amp; operations");
  expect(collectionsHtml).toContain("Replica-safe provider budget");

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
