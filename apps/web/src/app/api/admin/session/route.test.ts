import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("../../../../lib/admin-access", () => ({
  adminSessionStatus: vi.fn(),
}));

import { adminSessionStatus } from "../../../../lib/admin-access";
import {
  ADMIN_ROUTE_CACHE_COOKIE_NAME,
  ADMIN_ROUTE_CACHE_SECONDS,
  verifyAdminRouteCacheCookie,
} from "../../../../lib/route-auth-cache";
import { CUSTOMER_SESSION_COOKIE_NAME } from "../../../../lib/route-access-policy";

import { GET } from "./route";

const routeSecret = "unit-route-cache-secret";
const sessionCookie = "sealed-customer-session";

function adminRouteCacheFromSetCookie(setCookie: string | null): string {
  const match = setCookie?.match(
    new RegExp(`${ADMIN_ROUTE_CACHE_COOKIE_NAME}=([^;]+)`),
  );
  if (!match?.[1]) throw new Error("Missing admin route cache cookie");
  return match[1];
}

const adminSessionStatusMock = vi.mocked(adminSessionStatus);

describe("/api/admin/session route", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("sets an admin route cache after customer system-admin verification", async () => {
    vi.stubEnv("PRODUCT_PACK_SESSION_SECRET", routeSecret);
    adminSessionStatusMock.mockResolvedValue({
      authenticated: true,
      configured: true,
      customer: {
        email: "brian@cpghero.com",
        permissions: ["system.admin"],
        roles: ["account_owner", "system_owner"],
      },
      source: "customer_system",
    });

    const response = await GET(
      new Request("https://app.cpghero.com/api/admin/session", {
        headers: {
          cookie: `${CUSTOMER_SESSION_COOKIE_NAME}=${sessionCookie}`,
        },
      }),
    );

    expect(response.status).toBe(200);
    const setCookie = response.headers.get("set-cookie");
    expect(setCookie).toContain(`${ADMIN_ROUTE_CACHE_COOKIE_NAME}=`);
    expect(setCookie).toContain(`Max-Age=${ADMIN_ROUTE_CACHE_SECONDS}`);
    const cacheCookie = adminRouteCacheFromSetCookie(setCookie);
    await expect(
      verifyAdminRouteCacheCookie(cacheCookie, sessionCookie, routeSecret),
    ).resolves.toBe(true);
  });

  it("does not set an admin route cache for non-system customers", async () => {
    vi.stubEnv("PRODUCT_PACK_SESSION_SECRET", routeSecret);
    adminSessionStatusMock.mockResolvedValue({
      authenticated: false,
      configured: true,
      customer: {
        email: "owner@example.com",
        permissions: ["analytics.view"],
        roles: ["account_owner"],
      },
      source: "none",
    });

    const response = await GET(
      new Request("https://app.cpghero.com/api/admin/session", {
        headers: {
          cookie: `${CUSTOMER_SESSION_COOKIE_NAME}=${sessionCookie}`,
        },
      }),
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it("does not set an admin route cache for the legacy admin session source", async () => {
    vi.stubEnv("PRODUCT_PACK_SESSION_SECRET", routeSecret);
    adminSessionStatusMock.mockResolvedValue({
      authenticated: true,
      configured: true,
      source: "legacy_admin",
    });

    const response = await GET(
      new Request("https://app.cpghero.com/api/admin/session", {
        headers: {
          cookie: `${CUSTOMER_SESSION_COOKIE_NAME}=${sessionCookie}`,
        },
      }),
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("set-cookie")).toBeNull();
  });
});
