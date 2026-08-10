import { describe, expect, it } from "vitest";

import { displayDate } from "./presentation";

describe("displayDate", () => {
  it("uses an explicit display timezone on the server and browser", () => {
    expect(displayDate("2026-08-10T04:07:00Z")).toBe("Aug 9, 2026, 11:07 PM");
  });
});
