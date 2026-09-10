import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const analysesPageSource = readFileSync(
  new URL("../app/analyses/page.tsx", import.meta.url),
  "utf8",
);

const canonicalWorkspaceSource = readFileSync(
  new URL(
    "../app/analyses/[analysisId]/canonical-report-workspace.tsx",
    import.meta.url,
  ),
  "utf8",
);

const stylesSource = readFileSync(
  new URL("../app/styles.css", import.meta.url),
  "utf8",
);
const analysesPageText = analysesPageSource.replace(/\s+/g, " ");

describe("analyses library canonical preview source contract", () => {
  it("keeps the current report as the primary library action", () => {
    expect(analysesPageSource).toContain("Open current report");
    expect(analysesPageSource).toContain(
      "href={`/analyses/${encodeURIComponent(summary.analysis.analysis_id)}`}",
    );
  });

  it("exposes the simplified preview only for AnalysisResult v2 cards", () => {
    expect(analysesPageSource).toContain(
      'summary.analysis.schema_version === "2.0.0"',
    );
    expect(analysesPageSource).toContain("Open simplified preview");
    expect(analysesPageSource).toContain("?experience=canonical");
  });

  it("keeps a current-report comparison link inside the canonical preview", () => {
    expect(canonicalWorkspaceSource).toContain("Current report");
    expect(canonicalWorkspaceSource).toContain("?experience=legacy");
  });

  it("styles the preview action without making it the only visible action", () => {
    expect(stylesSource).toContain(".report-library-actions");
    expect(stylesSource).toContain(".canonical-preview-action");
  });

  it("explains empty report-library states with actionable diagnostics", () => {
    expect(analysesPageSource).toContain("Reports could not be loaded");
    expect(analysesPageSource).toContain(
      "No published AnalysisResults were returned",
    );
    expect(analysesPageSource).toContain("report-empty-diagnostics");
    expect(analysesPageSource).toContain("Materialization and readiness");
    expect(analysesPageText).toContain(
      "Filters cannot hide reports when the API returns zero report records",
    );
    expect(analysesPageSource).toContain(
      "No loaded reports match the current filters",
    );
    expect(stylesSource).toContain(".report-empty-diagnostics");
    expect(stylesSource).toContain(".report-filter-empty");
  });

  it("links empty report-library states to concrete follow-up workspaces", () => {
    expect(analysesPageSource).toContain("Review collection runs");
    expect(analysesPageSource).toContain('href="/collections"');
    expect(analysesPageSource).toContain("Check report materialization");
    expect(analysesPageSource).toContain('href="/admin/report-publishing"');
    expect(analysesPageSource).toContain("Review data quality");
    expect(analysesPageSource).toContain('href="/data-quality"');
    expect(stylesSource).toContain(".report-empty-diagnostics a");
  });
});
