import { expect, test } from "@playwright/test";

const queue = {
  queue_id: "test-queue",
  version: "1.0.0",
  product_pack: { id: "fresh_fluid_milk", version: "1.0.0" },
  case_count: 30,
  reviewed_case_count: 0,
  adjudicated_case_count: 0,
  created_at: "2026-08-15T00:00:00Z",
};

function listing(retailerId: string, index: number) {
  return {
    listing_id: `${retailerId}-${index}`,
    retailer_id: retailerId,
    retailer_product_id: `${retailerId}-product-${index}`,
    title: `${retailerId} milk ${index}`,
    brand: null,
    brand_type: "unclassified",
    brand_verified: false,
    image_url: null,
    product_url: null,
    attributes: {},
  };
}

const cases = Array.from({ length: 30 }, (_, index) => ({
  case_id: `case-${index}`,
  stratum: "exact_specification",
  critical: false,
  benchmark_listing: listing("walmart_us", index),
  competitor_listing: listing("aldi_us", index),
  engine_proposal: {
    tier: "exact_specification",
    status: "proposed",
    decision_reason: "Fixture proposal",
    evidence_coverage: { critical_coverage: 1 },
  },
  edge: { attribute_evidence: [] },
  evidence_refs: [],
  review_status: "pending",
  review_submissions: [],
  adjudication: null,
  ai_draft: null,
}));

test("explains the reviewer prerequisite before a bounded AI review", async ({
  page,
}) => {
  let aiDraftRequests = 0;
  await page.route("**/api/admin/session", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ configured: true, authenticated: true }),
    });
  });
  await page.route("**/api/admin/matching-v2/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "POST") {
      aiDraftRequests += 1;
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ error: "The confirmation must not submit." }),
      });
      return;
    }
    if (url.pathname === "/api/admin/matching-v2/review-queues") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ queues: [queue] }),
      });
      return;
    }
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        authoritative: false,
        queue,
        ai_review_policy: {
          enabled: true,
          model_id: "gpt-5.6-terra",
          max_batch_cases: 25,
          max_request_cost_usd: 0.35,
          vision_policy: "missing_or_conflicting_critical_evidence_only",
          authoritative: false,
          human_review_required: true,
        },
        status_counts: { adjudicated: 0 },
        competitor_retailers: [{ retailer_id: "aldi_us", case_count: 30 }],
        total_cases: 30,
        selected_case_count: 30,
        offset: 0,
        limit: 50,
        cases,
      }),
    });
  });

  await page.goto("/admin/matching-v2");
  const batch = page.getByRole("region", {
    name: "AI review drafts for selected cases",
  });
  await batch
    .getByRole("checkbox", { name: /Select eligible cases on this page/ })
    .check();
  await expect(batch.getByText("25", { exact: true })).toBeVisible();
  await expect(batch.getByText("$8.75", { exact: false })).toBeVisible();

  const reviewButton = batch.getByRole("button", {
    name: "Review 25 selected with AI",
  });
  await expect(reviewButton).toBeEnabled();
  await expect(
    batch.getByText("Enter your reviewer identity above to continue."),
  ).toBeVisible();

  await reviewButton.click();
  const reviewer = page.getByRole("textbox", {
    name: "Current reviewer identity",
  });
  await expect(reviewer).toBeFocused();
  await expect(
    page.getByText(
      "Enter your reviewer identity before reviewing selected cases with AI.",
    ),
  ).toBeVisible();

  await reviewer.fill("reviewer@cpghero.com");
  await reviewButton.click();
  await expect(batch.getByText("Queue 25 advisory drafts?")).toBeVisible();
  await expect(
    batch.getByRole("button", { name: "Confirm advisory review" }),
  ).toBeVisible();
  expect(aiDraftRequests).toBe(0);
});
