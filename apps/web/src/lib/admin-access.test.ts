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
  it("accepts the existing legacy admin session cookie", () => {
    configureLegacyAdmin();
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const request = new Request("https://app.cpghero.com/admin/matching-v2", {
      headers: {
        cookie: `${adminSessionCookie.name}=${createAdminSession()}`,
      },
    });

    expect(verifyAdminAccess(request)).toBe(true);
    expect(adminSessionStatus(request)).toEqual({
      authenticated: true,
      configured: true,
      source: "legacy_admin",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not accept WorkOS customer cookies as admin access", () => {
    configureLegacyAdmin();
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const request = new Request("https://app.cpghero.com/admin/matching-v2", {
      headers: { cookie: "cph_customer_session=sealed-session" },
    });

    expect(verifyAdminAccess(request)).toBe(false);
    expect(adminSessionStatus(request)).toEqual({
      authenticated: false,
      configured: true,
      source: "none",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("fails closed when no administrator session cookie is present", () => {
    configureLegacyAdmin();
    const fetchMock = vi.spyOn(globalThis, "fetch");

    expect(
      adminSessionStatus(
        new Request("https://app.cpghero.com/admin/matching-v2"),
      ),
    ).toEqual({
      authenticated: false,
      configured: true,
      source: "none",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
