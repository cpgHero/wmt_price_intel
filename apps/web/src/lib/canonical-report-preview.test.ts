import { describe, expect, it } from "vitest";

import { canonicalReportPreviewEnabled } from "./canonical-report-preview";

describe("canonicalReportPreviewEnabled", () => {
  it("keeps the simplified report hidden by default", () => {
    expect(canonicalReportPreviewEnabled(undefined, {})).toBe(false);
    expect(canonicalReportPreviewEnabled({}, {})).toBe(false);
    expect(canonicalReportPreviewEnabled({ experience: "legacy" }, {})).toBe(
      false,
    );
  });

  it("enables the simplified report for explicit preview flags", () => {
    expect(canonicalReportPreviewEnabled({ experience: "canonical" }, {})).toBe(
      true,
    );
    expect(
      canonicalReportPreviewEnabled({ experience: "simplified" }, {}),
    ).toBe(true);
    expect(
      canonicalReportPreviewEnabled({ reportExperience: "canonical" }, {}),
    ).toBe(true);
    expect(canonicalReportPreviewEnabled({ canonical: "1" }, {})).toBe(true);
    expect(canonicalReportPreviewEnabled({ canonical: "true" }, {})).toBe(true);
  });

  it("can enable the simplified report by environment for staging rollout", () => {
    expect(
      canonicalReportPreviewEnabled({}, { RCI_CANONICAL_REPORT_DEFAULT: "1" }),
    ).toBe(true);
    expect(
      canonicalReportPreviewEnabled(
        {},
        { RCI_CANONICAL_REPORT_DEFAULT: "enabled" },
      ),
    ).toBe(true);
  });

  it("lets explicit legacy flags override the environment rollout flag", () => {
    const environment = { RCI_CANONICAL_REPORT_DEFAULT: "true" };

    expect(
      canonicalReportPreviewEnabled({ experience: "legacy" }, environment),
    ).toBe(false);
    expect(
      canonicalReportPreviewEnabled(
        { reportExperience: "current" },
        environment,
      ),
    ).toBe(false);
    expect(canonicalReportPreviewEnabled({ canonical: "0" }, environment)).toBe(
      false,
    );
  });
});
