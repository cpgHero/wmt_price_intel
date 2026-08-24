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
    observed_location_count: index + 1,
    attributes: {},
  };
}

const aiStatuses = ["queued", "running", "succeeded", "needs_review"];
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
  final_decision: null,
  adjudication: null,
  ai_draft:
    index < aiStatuses.length
      ? {
          id: `ai-draft-${index}`,
          status: aiStatuses[index],
          model_id: "gpt-5.6-terra",
          requested_by: "fixture@cpghero.com",
        }
      : null,
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
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          authoritative: false,
          human_review_required: true,
          tasks: [],
        }),
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
        ai_review_summary: {
          active_task_count: 2,
          status_counts: {
            queued: 1,
            running: 1,
            succeeded: 1,
            needs_review: 1,
          },
          latest_batch: {
            id: "batch-1",
            requested_by: "fixture@cpghero.com",
            model_id: "gpt-5.6-terra",
            requested_case_count: 4,
            task_count: 4,
            queued: 1,
            running: 1,
            succeeded: 1,
            needs_review: 1,
            completed_count: 2,
            progress_percent: 50,
            estimated_seconds_remaining: 90,
            estimated_cost_usd: 0.1234,
            submitted_at: "2026-08-16T12:00:00Z",
            started_at: "2026-08-16T12:00:02Z",
            last_activity_at: "2026-08-16T12:01:00Z",
            completed_at: null,
          },
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
  const statusSummary = batch.locator(".cert-ai-status-summary");
  await expect(statusSummary).toContainText("1 queued");
  await expect(statusSummary).toContainText("1 reviewing");
  await expect(statusSummary).toContainText("1 drafts ready");
  await expect(statusSummary).toContainText("1 needs attention");
  await expect(statusSummary).toContainText(
    "Latest batch · 2 of 4 reached a terminal state",
  );
  await expect(statusSummary).toContainText("1 drafts ready · 1 failed");
  await expect(statusSummary).toContainText("Estimated remaining: About 2 min");
  await expect(statusSummary).toContainText("Recorded cost $0.1234");
  await expect(
    page.getByText("1 observed stores/locations").first(),
  ).toBeVisible();
  await expect(statusSummary).toContainText(
    "Queue-wide status refreshes automatically",
  );
  await expect(
    statusSummary.getByRole("button", { name: "Refresh AI status" }),
  ).toBeVisible();
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
  await batch.getByRole("button", { name: "Confirm advisory review" }).click();
  await expect(
    page.getByText(
      "25 AI review drafts were accepted. Status refreshes automatically while the work is queued or running.",
    ),
  ).toBeVisible();
  expect(aiDraftRequests).toBe(1);
});

test("prepares and confirms every eligible case in the retailer-scoped queue", async ({
  page,
}) => {
  let submittedCaseIds: string[] = [];
  await page.route("**/api/admin/session", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ configured: true, authenticated: true }),
    });
  });
  await page.route("**/api/admin/matching-v2/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith("/ai-drafts/eligible-cases")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          queue_id: queue.queue_id,
          competitor_retailer_id: "aldi_us",
          eligible_case_count: 26,
          selected_case_count: 26,
          deferred_case_count: 0,
          case_ids: cases.slice(4).map((reviewCase) => reviewCase.case_id),
          authoritative: false,
          human_review_required: true,
        }),
      });
      return;
    }
    if (request.method() === "POST" && url.pathname.endsWith("/ai-drafts")) {
      submittedCaseIds = (request.postDataJSON() as { case_ids: string[] })
        .case_ids;
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          authoritative: false,
          human_review_required: true,
          requested_case_count: submittedCaseIds.length,
          tasks: [],
        }),
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
          max_batch_cases: 1500,
          queue_wide_selection: true,
          queue_wide_scope: "current_queue_and_competitor_filter",
          max_request_cost_usd: 0.35,
          max_retry_rounds: 4,
          retryable_statuses: ["needs_review"],
          retry_preserves_history: true,
          retry_blocks_integrity_failures: true,
          vision_policy: "missing_or_conflicting_critical_evidence_only",
          authoritative: false,
          human_review_required: true,
        },
        ai_review_summary: {
          active_task_count: 0,
          status_counts: {
            queued: 1,
            running: 1,
            succeeded: 1,
            needs_review: 1,
          },
          latest_batch: null,
        },
        status_counts: { pending: 30 },
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
  await page
    .getByRole("textbox", { name: "Current reviewer identity" })
    .fill("reviewer@cpghero.com");
  await page
    .getByRole("combobox", { name: "Competitor retailer" })
    .selectOption("aldi_us");
  const batch = page.getByRole("region", {
    name: "AI review drafts for selected cases",
  });
  await batch
    .getByRole("button", { name: "Review all eligible Aldi Us cases" })
    .click();

  await expect(batch.getByText("Queue 26 advisory drafts?")).toBeVisible();
  await expect(batch.getByText("worst-case policy exposure")).toContainText(
    "$9.10",
  );
  expect(submittedCaseIds).toHaveLength(0);
  await batch.getByRole("button", { name: "Confirm advisory review" }).click();
  expect(submittedCaseIds).toHaveLength(26);
  await expect(
    page.getByText(
      "26 AI review drafts were accepted from the queue-wide eligible scope. Status refreshes automatically while the work is queued or running.",
    ),
  ).toBeVisible();
});

test("retries terminal AI failures as confirmed linked individual or bulk work", async ({
  page,
}) => {
  const retryPayloads: Array<Record<string, unknown>> = [];
  const terminalCases = [0, 1].map((index) => ({
    ...cases[index + 4],
    ai_draft: {
      id: `failed-ai-${index}`,
      batch_id: "failed-batch",
      status: "needs_review",
      model_id: "gpt-5.6-terra",
      requested_by: "fixture@cpghero.com",
      usage: { estimated_cost_usd: 0.031 + index / 1000 },
      attempt_count: 2,
      max_attempts: 2,
      retry_of_task_id: null,
      retry_sequence: 0,
      retry_reason: null,
      last_error_type: "TimeoutError",
      last_error_message: "Provider timed out before returning output.",
      created_at: "2026-08-16T12:00:00Z",
      updated_at: "2026-08-16T12:02:00Z",
    },
  }));

  await page.route("**/api/admin/session", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ configured: true, authenticated: true }),
    });
  });
  await page.route("**/api/admin/matching-v2/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith("/ai-drafts/retry")) {
      retryPayloads.push(request.postDataJSON() as Record<string, unknown>);
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          authoritative: false,
          human_review_required: true,
          history_preserved: true,
          requested_case_count: (
            request.postDataJSON() as { case_ids: string[] }
          ).case_ids.length,
        }),
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
          max_retry_rounds: 3,
          retryable_statuses: ["needs_review"],
          retry_preserves_history: true,
          retry_blocks_integrity_failures: true,
          vision_policy: "missing_or_conflicting_critical_evidence_only",
          authoritative: false,
          human_review_required: true,
        },
        ai_review_summary: {
          active_task_count: 0,
          status_counts: {
            queued: 0,
            running: 0,
            succeeded: 0,
            needs_review: 2,
          },
          latest_batch: null,
        },
        status_counts: { pending: 2 },
        competitor_retailers: [{ retailer_id: "aldi_us", case_count: 2 }],
        total_cases: 2,
        selected_case_count: 2,
        offset: 0,
        limit: 50,
        cases: terminalCases,
      }),
    });
  });

  await page.goto("/admin/matching-v2");
  await page
    .getByRole("textbox", { name: "Current reviewer identity" })
    .fill("reviewer@cpghero.com");
  await page
    .getByRole("button", { name: "Retry 2 needs-attention items" })
    .click();
  await expect(page.getByText("Retry 2 terminal AI failures?")).toBeVisible();
  await expect(
    page.getByText("Maximum new policy exposure: $0.70"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Confirm governed retry" }).click();
  expect(retryPayloads[0]).toMatchObject({
    requested_by: "reviewer@cpghero.com",
    case_ids: [terminalCases[0].case_id, terminalCases[1].case_id],
  });

  await page.getByRole("button", { name: "Review evidence" }).first().click();
  const drawer = page.getByRole("dialog", { name: "Match evidence review" });
  await expect(drawer).toContainText(
    "Provider timed out before returning output.",
  );
  await drawer
    .getByRole("button", { name: "Retry AI evidence review" })
    .click();
  await expect(drawer).toContainText("Prior attempts, this exact error");
  await drawer.getByRole("button", { name: "Confirm governed retry" }).click();
  expect(retryPayloads[1]).toMatchObject({
    requested_by: "reviewer@cpghero.com",
    case_ids: [terminalCases[0].case_id],
  });
});

test("bulk-certifies comparable and not-comparable AI recommendations", async ({
  page,
}) => {
  let commitPayload: Record<string, unknown> | null = null;
  const readyCases = [0, 1, 2].map((index) => ({
    ...cases[index + 4],
    benchmark_listing:
      index === 2
        ? {
            ...cases[index + 4].benchmark_listing,
            seller_governance: { status: "excluded_third_party" },
          }
        : cases[index + 4].benchmark_listing,
    ai_draft: {
      id: `ready-ai-${index}`,
      batch_id: "batch-ready",
      status: "succeeded",
      model_id: "gpt-5.6-terra",
      requested_by: "fixture@cpghero.com",
      output_document: {
        authoritative: false,
        human_review_required: true,
        result: {
          verdict_proposal: index === 1 ? "not_comparable" : "comparable",
          tier_proposal: index === 1 ? null : "exact_specification",
          rationale: `Governed package evidence agrees for pair ${index + 1}.`,
          attribute_proposals: [],
          conflicts: [],
          requires_human_review: true,
        },
      },
      attempt_count: 1,
      max_attempts: 3,
      created_at: "2026-08-16T12:00:00Z",
      updated_at: "2026-08-16T12:01:00Z",
    },
  }));

  await page.route("**/api/admin/session", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ configured: true, authenticated: true }),
    });
  });
  await page.route("**/api/admin/matching-v2/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith("/ai-bulk-certification/preview")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          queue_id: queue.queue_id,
          queue_version: queue.version,
          policy: {
            id: "guarded_ai_recommendation_bulk_certification",
            version: "1.2.0",
            max_cases: 50,
            allowed_verdicts: ["comparable", "not_comparable"],
            allowed_tiers: [
              "exact_item",
              "exact_specification",
              "equivalent_product",
              "comparable_substitute",
              "custom_approved",
            ],
            minimum_critical_coverage: 1,
            minimum_ai_attribute_confidence: 0.85,
            checksum: "b".repeat(64),
            human_confirmation_required: true,
            automatically_changes_reporting: false,
          },
          requested_case_count: 3,
          eligible_case_count: 2,
          excluded_case_count: 1,
          eligible_cases: [
            {
              case_id: readyCases[0].case_id,
              eligible: true,
              reason_codes: [],
              reasons: [],
              warning_codes: ["ai_conflict_present"],
              warnings: [
                "The AI draft identifies one or more unresolved conflicts.",
              ],
              recommended_tier: "exact_specification",
              critical_coverage: 1,
              engine_status: "proposed",
              ai_task_id: "ready-ai-0",
              ai_rationale: "Governed package evidence agrees for pair 1.",
              benchmark_product: {
                retailer_id: "walmart_us",
                retailer_product_id: "walmart-product-4",
                title: "Walmart milk 4",
                brand: "Great Value",
                image_url: null,
                observed_location_count: 4200,
              },
              competitor_product: {
                retailer_id: "aldi_us",
                retailer_product_id: "aldi-product-4",
                title: "ALDI milk 4",
                brand: "Friendly Farms",
                image_url: null,
                observed_location_count: 1700,
              },
            },
            {
              case_id: readyCases[1].case_id,
              eligible: true,
              reason_codes: [],
              reasons: [],
              warning_codes: [],
              warnings: [],
              recommended_verdict: "not_comparable",
              recommended_tier: null,
              critical_coverage: 1,
              engine_status: "rejected",
              ai_task_id: "ready-ai-1",
              ai_rationale:
                "A material package-size conflict makes this pair not comparable.",
              benchmark_product: {
                retailer_id: "walmart_us",
                retailer_product_id: "walmart-product-5",
                title: "Walmart milk 5",
                brand: "Great Value",
                image_url: null,
                observed_location_count: 3900,
              },
              competitor_product: {
                retailer_id: "aldi_us",
                retailer_product_id: "aldi-product-5",
                title: "ALDI milk 5",
                brand: "Friendly Farms",
                image_url: null,
                observed_location_count: 1600,
              },
            },
          ],
          excluded_cases: [
            {
              case_id: readyCases[2].case_id,
              eligible: false,
              reason_codes: ["known_third_party_seller"],
              reasons: [
                "A known third-party marketplace seller makes the listing ineligible.",
              ],
              warning_codes: [],
              warnings: [],
              recommended_verdict: "comparable",
              recommended_tier: "exact_specification",
              critical_coverage: 1,
              engine_status: "proposed",
              ai_task_id: "ready-ai-2",
              ai_rationale: "The governed package evidence otherwise agrees.",
              benchmark_product: {
                retailer_id: "walmart_us",
                retailer_product_id: "marketplace-product",
                title: "Marketplace milk",
                brand: "Third Party",
                image_url: null,
                observed_location_count: 20,
              },
              competitor_product: {
                retailer_id: "aldi_us",
                retailer_product_id: "aldi-product-6",
                title: "ALDI milk 6",
                brand: "Friendly Farms",
                image_url: null,
                observed_location_count: 1400,
              },
            },
          ],
          exclusion_summary: [
            {
              reason_code: "known_third_party_seller",
              reason:
                "A known third-party marketplace seller makes the listing ineligible.",
              case_count: 1,
            },
          ],
          warning_summary: [
            {
              warning_code: "ai_conflict_present",
              warning:
                "The AI draft identifies one or more unresolved conflicts.",
              case_count: 1,
            },
          ],
          confirmation_checksum: "a".repeat(64),
          human_confirmation_required: true,
          final_until_flagged: true,
          automatically_changes_reporting: false,
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/ai-bulk-certification/commit")) {
      commitPayload = request.postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          action_id: "bulk-action-1",
          certified_case_count: 2,
          certified_case_ids: [readyCases[0].case_id, readyCases[1].case_id],
          comparable_case_count: 1,
          not_comparable_case_count: 1,
          approved_case_count: 2,
          approved_case_ids: [readyCases[0].case_id, readyCases[1].case_id],
          idempotent_replay: false,
        }),
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
        ai_bulk_certification_policy: {
          id: "guarded_ai_recommendation_bulk_certification",
          version: "1.2.0",
          max_cases: 50,
          allowed_verdicts: ["comparable", "not_comparable"],
          allowed_tiers: [
            "exact_item",
            "exact_specification",
            "equivalent_product",
            "comparable_substitute",
            "custom_approved",
          ],
          minimum_critical_coverage: 1,
          minimum_ai_attribute_confidence: 0.85,
          checksum: "b".repeat(64),
          human_confirmation_required: true,
          automatically_changes_reporting: false,
        },
        ai_review_summary: {
          active_task_count: 0,
          status_counts: {
            queued: 0,
            running: 0,
            succeeded: 3,
            needs_review: 0,
          },
          latest_batch: null,
        },
        status_counts: { pending: 3 },
        competitor_retailers: [{ retailer_id: "aldi_us", case_count: 3 }],
        total_cases: 3,
        selected_case_count: 3,
        offset: 0,
        limit: 50,
        cases: readyCases,
      }),
    });
  });

  await page.goto("/admin/matching-v2");
  await page
    .getByRole("textbox", { name: "Current reviewer identity" })
    .fill("reviewer@cpghero.com");
  const bulkSection = page.getByRole("region", {
    name: "Bulk accept AI certification recommendations",
  });
  await bulkSection
    .getByRole("button", { name: "Assess queue-wide recommendations" })
    .click();
  const preview = page.getByRole("region", {
    name: "Bulk certification preview",
  });
  await expect(preview).toContainText("2 eligible · 1 excluded");
  await expect(preview).toContainText("Walmart milk 4");
  await expect(preview).toContainText("Walmart milk 5");
  await expect(preview.getByText("matches", { exact: true })).toBeVisible();
  await expect(preview).toContainText("is not comparable with");
  await preview.getByText(/Why 1 case was excluded/).click();
  await expect(preview).toContainText(
    "A known third-party marketplace seller makes the listing ineligible.",
  );
  await expect(preview).toContainText(
    "The AI draft identifies one or more unresolved conflicts.",
  );
  await preview
    .getByRole("button", { name: "Finalize 2 recommendations" })
    .click();
  await expect(
    page.getByText(
      "2 AI recommendations were accepted by reviewer@cpghero.com and finalized (1 comparable, 1 not comparable). Reporting is not recalculated automatically; each decision remains final until flagged.",
    ),
  ).toBeVisible();
  expect(commitPayload).toMatchObject({
    reviewer_id: "reviewer@cpghero.com",
    case_ids: [readyCases[0].case_id, readyCases[1].case_id],
    confirmation_checksum: "a".repeat(64),
  });
});

test("discovers not-comparable AI recommendations beyond the visible page", async ({
  page,
}) => {
  const attentionCases = Array.from({ length: 50 }, (_, index) => ({
    ...cases[index % cases.length],
    case_id: `attention-${index}`,
    review_status: "pending",
    ai_draft: {
      id: `attention-ai-${index}`,
      status: "needs_review",
      model_id: "gpt-5.6-terra",
      requested_by: "fixture@cpghero.com",
      output_document: null,
      attempt_count: 2,
      max_attempts: 2,
      retry_sequence: 0,
      created_at: "2026-08-16T12:00:00Z",
      updated_at: "2026-08-16T12:01:00Z",
    },
  }));
  const affirmative = {
    ...cases[4],
    case_id: "affirmative-on-second-page",
    review_status: "pending",
    ai_draft: {
      id: "ready-ai-second-page",
      status: "succeeded",
      model_id: "gpt-5.6-terra",
      requested_by: "fixture@cpghero.com",
      output_document: {
        authoritative: false,
        human_review_required: true,
        result: {
          verdict_proposal: "not_comparable",
          tier_proposal: null,
          rationale:
            "The structured package evidence contains a material conflict.",
          attribute_proposals: [],
          conflicts: [],
          requires_human_review: true,
        },
      },
      attempt_count: 1,
      max_attempts: 2,
      created_at: "2026-08-16T12:00:00Z",
      updated_at: "2026-08-16T12:01:00Z",
    },
  };
  let previewPayload: Record<string, unknown> | null = null;

  await page.route("**/api/admin/session", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ configured: true, authenticated: true }),
    });
  });
  await page.route("**/api/admin/matching-v2/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith("/ai-bulk-certification/preview")) {
      previewPayload = request.postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          queue_id: queue.queue_id,
          queue_version: queue.version,
          policy: {
            id: "guarded_ai_recommendation_bulk_certification",
            version: "1.2.0",
            max_cases: 50,
            allowed_verdicts: ["comparable", "not_comparable"],
            allowed_tiers: ["exact_specification"],
            minimum_critical_coverage: 1,
            minimum_ai_attribute_confidence: 0.85,
            checksum: "b".repeat(64),
            human_confirmation_required: true,
            automatically_changes_reporting: false,
          },
          requested_case_count: 1,
          eligible_case_count: 1,
          excluded_case_count: 0,
          eligible_cases: [
            {
              case_id: affirmative.case_id,
              eligible: true,
              reason_codes: [],
              reasons: [],
              warning_codes: [],
              warnings: [],
              recommended_verdict: "not_comparable",
              recommended_tier: null,
              critical_coverage: 1,
              engine_status: "proposed",
              ai_task_id: "ready-ai-second-page",
              ai_rationale:
                "The structured package evidence contains a material conflict.",
              benchmark_product: {
                retailer_id: "walmart_us",
                retailer_product_id: "walmart-product-4",
                title: "Walmart milk 4",
                brand: "Great Value",
                image_url: null,
                observed_location_count: 4200,
              },
              competitor_product: {
                retailer_id: "aldi_us",
                retailer_product_id: "aldi-product-4",
                title: "ALDI milk 4",
                brand: "Friendly Farms",
                image_url: null,
                observed_location_count: 1700,
              },
            },
          ],
          excluded_cases: [],
          exclusion_summary: [],
          warning_summary: [],
          confirmation_checksum: "a".repeat(64),
          human_confirmation_required: true,
          final_until_flagged: true,
          automatically_changes_reporting: false,
        }),
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
    const offset = Number(url.searchParams.get("offset") ?? 0);
    const discovery = url.searchParams.get("limit") === "500";
    const responseCases = discovery
      ? offset === 0
        ? [...attentionCases, affirmative]
        : []
      : attentionCases;
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
          max_retry_rounds: 4,
          retryable_statuses: ["needs_review"],
          retry_preserves_history: true,
          retry_blocks_integrity_failures: true,
          vision_policy: "missing_or_conflicting_critical_evidence_only",
          authoritative: false,
          human_review_required: true,
        },
        ai_bulk_certification_policy: {
          id: "guarded_ai_recommendation_bulk_certification",
          version: "1.2.0",
          max_cases: 50,
          allowed_verdicts: ["comparable", "not_comparable"],
          allowed_tiers: ["exact_specification"],
          minimum_critical_coverage: 1,
          minimum_ai_attribute_confidence: 0.85,
          checksum: "b".repeat(64),
          human_confirmation_required: true,
          automatically_changes_reporting: false,
        },
        ai_review_summary: {
          active_task_count: 0,
          status_counts: {
            queued: 0,
            running: 0,
            succeeded: 1,
            needs_review: 50,
          },
          latest_batch: null,
        },
        status_counts: { pending: 51 },
        competitor_retailers: [{ retailer_id: "aldi_us", case_count: 51 }],
        total_cases: 51,
        selected_case_count: 51,
        offset,
        limit: discovery ? 500 : 50,
        cases: responseCases,
      }),
    });
  });

  await page.goto("/admin/matching-v2");
  await page
    .getByRole("textbox", { name: "Current reviewer identity" })
    .fill("reviewer@cpghero.com");
  await page
    .getByRole("button", { name: "Assess queue-wide recommendations" })
    .click();
  await expect(
    page.getByRole("region", { name: "Bulk certification preview" }),
  ).toBeVisible();
  expect(previewPayload).toMatchObject({
    case_ids: ["affirmative-on-second-page"],
  });
});

test("reports a plain-text submission failure without a JSON parsing error", async ({
  page,
}) => {
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
      await route.fulfill({
        status: 500,
        contentType: "text/plain",
        body: "Internal Server Error",
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
        status_counts: { pending: 1 },
        competitor_retailers: [{ retailer_id: "aldi_us", case_count: 1 }],
        total_cases: 1,
        selected_case_count: 1,
        offset: 0,
        limit: 50,
        cases: [
          {
            ...cases[4],
            ai_draft: null,
            evidence_refs: ["source-file:test.csv#sha256=test"],
          },
        ],
      }),
    });
  });

  await page.goto("/admin/matching-v2");
  await page
    .getByRole("textbox", { name: "Current reviewer identity" })
    .fill("reviewer@cpghero.com");
  await page.getByRole("button", { name: "Review evidence" }).click();
  const drawer = page.getByRole("dialog", { name: "Match evidence review" });
  await drawer.getByRole("button", { name: "Approve match" }).click();
  await drawer
    .getByRole("textbox", { name: "Evidence rationale" })
    .fill("The governed package attributes agree.");
  await drawer.getByRole("button", { name: "Save final decision" }).click();

  const submissionError = page.locator(".cert-error");
  await expect(submissionError).toContainText("Internal Server Error (500)");
  await expect(submissionError).not.toContainText("Unexpected token");
});

test("blocks comparable approval when current Milk package volume conflicts", async ({
  page,
}) => {
  await page.route("**/api/admin/session", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ configured: true, authenticated: true }),
    });
  });
  await page.route("**/api/admin/matching-v2/**", async (route) => {
    const url = new URL(route.request().url());
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
        status_counts: { pending: 1 },
        competitor_retailers: [{ retailer_id: "aldi_us", case_count: 1 }],
        total_cases: 1,
        selected_case_count: 1,
        offset: 0,
        limit: 50,
        cases: [
          {
            ...cases[4],
            ai_draft: null,
            evidence_refs: ["source-file:test.csv#sha256=test"],
            edge: {
              attribute_evidence: [
                {
                  attribute: "volume_oz",
                  role: "hard_blocker",
                  queue_role: "soft_comparator",
                  role_source: "active_product_pack_certification_policy",
                  benchmark_value: 128,
                  competitor_value: 64,
                  outcome: "conflict",
                  benchmark_source: "pdp:walmart_us:w1",
                  competitor_source: "pdp:aldi_us:a1",
                  reliability: 0.95,
                },
              ],
            },
            certification_blockers: [
              {
                attribute: "volume_oz",
                outcome: "conflict",
                benchmark_value: 128,
                competitor_value: 64,
                reason: "Current Product Pack requires exact volume.",
              },
            ],
          },
        ],
      }),
    });
  });

  await page.goto("/admin/matching-v2");
  await expect(page.getByText("Package size blocked")).toBeVisible();
  await page.getByRole("button", { name: "Review evidence" }).click();
  const drawer = page.getByRole("dialog", { name: "Match evidence review" });
  await expect(
    drawer.getByRole("heading", {
      name: "This pair cannot be approved as comparable",
    }),
  ).toBeVisible();
  await expect(drawer.getByText("128 versus 64 · Conflict")).toBeVisible();
  await expect(
    drawer.getByRole("button", { name: "Approve match" }),
  ).toBeDisabled();
  await expect(
    drawer.getByRole("button", { name: "Reject match" }),
  ).toBeEnabled();
});

test("finalizes one human decision and requires an explicit flag before review", async ({
  page,
}) => {
  const submittedVerdicts: string[] = [];
  let reviewCase = {
    ...cases[4],
    ai_draft: null,
    evidence_refs: ["source-file:test.csv#sha256=test"],
  };
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
      const body = request.postDataJSON() as {
        reviewer_id: string;
        verdict: string;
        rationale: string;
      };
      submittedVerdicts.push(body.verdict);
      reviewCase = {
        ...reviewCase,
        review_status:
          body.verdict === "insufficient_evidence" ? "flagged" : "approved",
        final_decision: {
          id: `decision-${submittedVerdicts.length}`,
          source: "review_submission",
          reviewer_id: body.reviewer_id,
          verdict: body.verdict,
          allowed_tiers:
            body.verdict === "comparable" ? ["exact_specification"] : [],
          rationale: body.rationale,
          evidence_refs: reviewCase.evidence_refs,
        },
      };
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ id: `decision-${submittedVerdicts.length}` }),
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
        status_counts: {
          [reviewCase.review_status]: 1,
        },
        competitor_retailers: [{ retailer_id: "aldi_us", case_count: 1 }],
        total_cases: 1,
        selected_case_count: 1,
        offset: 0,
        limit: 50,
        cases: [reviewCase],
      }),
    });
  });

  await page.goto("/admin/matching-v2");
  await page
    .getByRole("textbox", { name: "Current reviewer identity" })
    .fill("reviewer@cpghero.com");
  await page.getByRole("button", { name: "Review evidence" }).click();
  let drawer = page.getByRole("dialog", { name: "Match evidence review" });
  await drawer.getByRole("button", { name: "Approve match" }).click();
  await drawer
    .getByRole("textbox", { name: "Evidence rationale" })
    .fill("The governed package attributes agree.");
  await drawer.getByRole("button", { name: "Save final decision" }).click();
  await expect(
    page.getByText(
      "Match approved and finalized. It remains final unless someone flags it.",
    ),
  ).toBeVisible();
  await page.getByLabel("Queue status").selectOption("approved");
  await page.getByRole("button", { name: "View decision" }).click();
  drawer = page.getByRole("dialog", { name: "Match evidence review" });
  await drawer
    .getByRole("textbox", { name: "Reason to flag this decision" })
    .fill("The new package image conflicts with the approved attributes.");
  await drawer.getByRole("button", { name: "Flag for re-review" }).click();

  await expect(
    page.getByText("Case flagged and returned to the review queue."),
  ).toBeVisible();
  expect(submittedVerdicts).toEqual(["comparable", "insufficient_evidence"]);
});
