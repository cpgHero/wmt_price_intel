import { describe, expect, it } from "vitest";

import { canonicalReportExperienceEnabled } from "./canonical-report-experience";

describe("canonicalReportExperienceEnabled", () => {
  it("uses the legacy report by default", () => {
    expect(canonicalReportExperienceEnabled(undefined, {})).toBe(false);
    expect(canonicalReportExperienceEnabled({}, {})).toBe(false);
    expect(canonicalReportExperienceEnabled({ experience: "legacy" }, {})).toBe(
      false,
    );
  });

  it("does not enable the discarded simplified report for explicit preview flags", () => {
    expect(
      canonicalReportExperienceEnabled({ experience: "canonical" }, {}),
    ).toBe(false);
    expect(
      canonicalReportExperienceEnabled({ experience: "simplified" }, {}),
    ).toBe(false);
    expect(
      canonicalReportExperienceEnabled({ reportExperience: "canonical" }, {}),
    ).toBe(false);
    expect(canonicalReportExperienceEnabled({ canonical: "1" }, {})).toBe(false);
    expect(canonicalReportExperienceEnabled({ canonical: "true" }, {})).toBe(
      false,
    );
  });

  it("ignores previous simplified-default environment flags", () => {
    expect(
      canonicalReportExperienceEnabled(
        {},
        { RCI_CANONICAL_REPORT_DEFAULT: "1" },
      ),
    ).toBe(false);
    expect(
      canonicalReportExperienceEnabled(
        {},
        { RCI_CANONICAL_REPORT_DEFAULT: "enabled" },
      ),
    ).toBe(false);
  });

  it("lets explicit legacy flags override the default report path", () => {
    const environment = { RCI_CANONICAL_REPORT_DEFAULT: "true" };

    expect(
      canonicalReportExperienceEnabled({ experience: "legacy" }, environment),
    ).toBe(false);
    expect(
      canonicalReportExperienceEnabled(
        { reportExperience: "current" },
        environment,
      ),
    ).toBe(false);
    expect(
      canonicalReportExperienceEnabled({ canonical: "0" }, environment),
    ).toBe(false);
  });

  it("allows an environment safety switch to restore the legacy report path", () => {
    expect(
      canonicalReportExperienceEnabled(
        {},
        { RCI_CANONICAL_REPORT_DEFAULT: "0" },
      ),
    ).toBe(false);
    expect(
      canonicalReportExperienceEnabled(
        {},
        { RCI_CANONICAL_REPORT_DEFAULT: "false" },
      ),
    ).toBe(false);
    expect(
      canonicalReportExperienceEnabled(
        {},
        { RCI_CANONICAL_REPORT_DEFAULT: "disabled" },
      ),
    ).toBe(false);
  });
});
