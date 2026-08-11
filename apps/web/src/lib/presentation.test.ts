import { describe, expect, it } from "vitest";

import { displayDate, displayLabel } from "./presentation";

describe("displayLabel", () => {
  it("uses the retailer catalog's user-facing names", () => {
    expect(displayLabel("albertsons_us")).toBe("Albertsons");
    expect(displayLabel("heb_us")).toBe("H-E-B");
    expect(displayLabel("sams_club_us")).toBe("Sam's Club");
    expect(displayLabel("shoprite_us")).toBe("ShopRite");
    expect(displayLabel("trader_joes_us")).toBe("Trader Joe's");
  });
});

describe("displayDate", () => {
  it("uses an explicit display timezone on the server and browser", () => {
    expect(displayDate("2026-08-10T04:07:00Z")).toBe("Aug 9, 2026, 11:07 PM");
  });
});
