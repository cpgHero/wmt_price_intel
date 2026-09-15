import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { adminSessionStatus, verifyAdminAccess } from "./admin-access";
import { adminSessionCookie, createAdminSession } from "./admin-session";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

function configureLegacyAdmin() {
  vi.stubEnv("PRODUCT_PACK_ADMIN_PASSWORD", "admin-password");
  vi.stubEnv("PRODUCT_PACK_SESSION_SECRET", "admin-session-secret");
}

describe("admin access", () => {
  it("accepts the existing legacy admin session cookie", async () => {
    configureLegacyAdmin();
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const request = new Request("https://app.cpghero.com/admin/customer-auth", {
      headers: {
        cookie: `${adminSessionCookie.name}=${createAdminSession()}`,
      },
    });

    await expect(verifyAdminAccess(request)).resolves.toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("accepts a WorkOS-backed CPGHero principal with system admin permission", async () => {
    configureLegacyAdmin();
    vi.stubEnv("RCI_API_INTERNAL_URL", "http://api.internal");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({
        principal: {
          email: "owner@cpghero.com",
          permissions: ["system.admin", "system.governance"],
          roles: ["system_owner"],
        },
      }),
    );
    const request = new Request("https://app.cpghero.com/admin/customer-auth", {
      headers: { cookie: "cph_customer_session=sealed-session" },
    });

    await expect(adminSessionStatus(request)).resolves.toEqual({
      authenticated: true,
      configured: true,
      customer: {
        email: "owner@cpghero.com",
        permissions: ["system.admin", "system.governance"],
        roles: ["system_owner"],
      },
      source: "customer_system",
    });
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(
      "http://api.internal/api/v1/me",
    );
  });

  it("does not accept an account owner without system admin permission", async () => {
    configureLegacyAdmin();
    vi.stubEnv("RCI_API_INTERNAL_URL", "http://api.internal");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({
        principal: {
          email: "account-owner@example.com",
          permissions: ["analytics.view", "users.manage"],
          roles: ["account_owner"],
        },
      }),
    );
    const request = new Request("https://app.cpghero.com/admin/customer-auth", {
      headers: { cookie: "cph_customer_session=sealed-session" },
    });

    await expect(adminSessionStatus(request)).resolves.toEqual({
      authenticated: false,
      configured: true,
      customer: {
        email: "account-owner@example.com",
        permissions: ["analytics.view", "users.manage"],
        roles: ["account_owner"],
      },
      source: "none",
    });
  });

  it("fails closed when no administrator or customer session cookie is present", async () => {
    configureLegacyAdmin();
    const fetchMock = vi.spyOn(globalThis, "fetch");

    await expect(
      adminSessionStatus(
        new Request("https://app.cpghero.com/admin/customer-auth"),
      ),
    ).resolves.toEqual({
      authenticated: false,
      configured: true,
      source: "none",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
