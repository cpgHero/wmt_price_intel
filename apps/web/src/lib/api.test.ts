import { describe, expect, it } from "vitest";

import { apiErrorMessage } from "./api";

describe("apiErrorMessage", () => {
  it("surfaces a structured quarantine message instead of a bare 409", () => {
    expect(
      apiErrorMessage(409, {
        detail: {
          code: "legacy_availability_contract_quarantined",
          message:
            "This report is quarantined because it does not contain validated local-availability evidence.",
        },
      }),
    ).toBe(
      "This report is quarantined because it does not contain validated local-availability evidence.",
    );
  });

  it("preserves ordinary string errors and status-only fallbacks", () => {
    expect(apiErrorMessage(422, { detail: "Invalid request" })).toBe(
      "Invalid request",
    );
    expect(apiErrorMessage(503, "upstream unavailable")).toBe(
      "API returned 503",
    );
  });
});
