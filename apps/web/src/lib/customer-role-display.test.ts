import { describe, expect, it } from "vitest";

import { customerPrimaryRoleLabel } from "./customer-role-display";

describe("customerPrimaryRoleLabel", () => {
  it("prioritizes system owner over account owner for system administrators", () => {
    expect(customerPrimaryRoleLabel(["account_owner", "system_owner"])).toBe(
      "System owner",
    );
  });

  it("uses account owner when no system role is present", () => {
    expect(customerPrimaryRoleLabel(["viewer", "account_owner"])).toBe(
      "Account owner",
    );
  });

  it("falls back to an unknown role label or generic customer label", () => {
    expect(customerPrimaryRoleLabel(["custom_role"])).toBe("custom role");
    expect(customerPrimaryRoleLabel([])).toBe("Customer");
  });
});
