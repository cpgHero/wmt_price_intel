import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ADMIN_ROUTE_CACHE_COOKIE_NAME,
  CUSTOMER_ROUTE_CACHE_COOKIE_NAME,
  createAdminRouteCacheCookie,
  createCustomerRouteCacheCookie,
} from "./lib/route-auth-cache";
import { CUSTOMER_SESSION_COOKIE_NAME } from "./lib/route-access-policy";

import { proxy } from "./proxy";

const routeSecret = "unit-route-cache-secret";
const sessionCookie = "sealed-customer-session";

function requestWithCookie(pathname: string, cookie: string): NextRequest {
  return new NextRequest(`https://app.cpghero.com${pathname}`, {
    headers: { cookie },
  });
}

describe("proxy customer route authentication cache", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("uses a valid customer route cache without revalidating through /api/auth/me", async () => {
    vi.stubEnv("PRODUCT_PACK_SESSION_SECRET", routeSecret);
    const cacheCookie = await createCustomerRouteCacheCookie(
      sessionCookie,
      routeSecret,
    );
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const response = await proxy(
      requestWithCookie(
        "/proximity",
        `${CUSTOMER_SESSION_COOKIE_NAME}=${sessionCookie}; ${CUSTOMER_ROUTE_CACHE_COOKIE_NAME}=${cacheCookie}`,
      ),
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });

  it("recognizes quoted sealed customer cookies at the route boundary", async () => {
    vi.stubEnv("PRODUCT_PACK_SESSION_SECRET", routeSecret);
    const paddedSessionCookie = "sealed-customer-session.with=padding";
    const cacheCookie = await createCustomerRouteCacheCookie(
      paddedSessionCookie,
      routeSecret,
    );
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const response = await proxy(
      requestWithCookie(
        "/customer",
        `${CUSTOMER_SESSION_COOKIE_NAME}="${paddedSessionCookie}"; ${CUSTOMER_ROUTE_CACHE_COOKIE_NAME}=${cacheCookie}`,
      ),
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });

  it("sets the customer route cache after a successful customer session validation", async () => {
    vi.stubEnv("PRODUCT_PACK_SESSION_SECRET", routeSecret);
    const fetchSpy = vi
      .fn()
      .mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchSpy);

    const response = await proxy(
      requestWithCookie(
        "/proximity",
        `${CUSTOMER_SESSION_COOKIE_NAME}=${sessionCookie}`,
      ),
    );

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(String(fetchSpy.mock.calls[0]?.[0])).toBe(
      "https://app.cpghero.com/api/auth/me",
    );
    expect(response.headers.get("set-cookie")).toContain(
      `${CUSTOMER_ROUTE_CACHE_COOKIE_NAME}=`,
    );
  });

  it("fails closed to the customer login when the session and route cache are invalid", async () => {
    vi.stubEnv("PRODUCT_PACK_SESSION_SECRET", routeSecret);
    const fetchSpy = vi
      .fn()
      .mockResolvedValue(new Response("{}", { status: 401 }));
    vi.stubGlobal("fetch", fetchSpy);

    const response = await proxy(
      requestWithCookie(
        "/proximity",
        `${CUSTOMER_SESSION_COOKIE_NAME}=fake; ${CUSTOMER_ROUTE_CACHE_COOKIE_NAME}=tampered`,
      ),
    );

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "https://app.cpghero.com/api/auth/login?return_to=%2Fproximity",
    );
  });

  it("does not launch customer login for unauthenticated RSC route requests", async () => {
    vi.stubEnv("PRODUCT_PACK_SESSION_SECRET", routeSecret);
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const response = await proxy(
      new NextRequest("https://app.cpghero.com/proximity?_rsc=abc123", {
        headers: { rsc: "1" },
      }),
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(response.status).toBe(401);
    expect(response.headers.get("location")).toBeNull();
    expect(await response.json()).toEqual({
      error: "Customer authentication is required.",
    });
  });

  it("does not launch customer login for non-document protected route requests", async () => {
    vi.stubEnv("PRODUCT_PACK_SESSION_SECRET", routeSecret);
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const response = await proxy(
      new NextRequest("https://app.cpghero.com/proximity", {
        headers: { accept: "text/x-component" },
      }),
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(response.status).toBe(401);
    expect(response.headers.get("location")).toBeNull();
  });

  it("allows admin pages when the customer session has system admin access", async () => {
    vi.stubEnv("PRODUCT_PACK_SESSION_SECRET", routeSecret);
    const fetchSpy = vi.fn().mockResolvedValue(
      Response.json({
        authenticated: true,
        source: "customer_system",
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const response = await proxy(
      requestWithCookie(
        "/admin/matching-v2",
        `${CUSTOMER_SESSION_COOKIE_NAME}=${sessionCookie}`,
      ),
    );

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(String(fetchSpy.mock.calls[0]?.[0])).toBe(
      "https://app.cpghero.com/api/admin/session",
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });

  it("uses a valid admin route cache without revalidating through /api/admin/session", async () => {
    vi.stubEnv("PRODUCT_PACK_SESSION_SECRET", routeSecret);
    const adminCacheCookie = await createAdminRouteCacheCookie(
      sessionCookie,
      routeSecret,
    );
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const response = await proxy(
      requestWithCookie(
        "/admin/matching-v2",
        `${CUSTOMER_SESSION_COOKIE_NAME}=${sessionCookie}; ${ADMIN_ROUTE_CACHE_COOKIE_NAME}=${adminCacheCookie}`,
      ),
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });

  it("does not accept a customer route cache as administrator route access", async () => {
    vi.stubEnv("PRODUCT_PACK_SESSION_SECRET", routeSecret);
    const customerCacheCookie = await createCustomerRouteCacheCookie(
      sessionCookie,
      routeSecret,
    );
    const fetchSpy = vi.fn().mockResolvedValue(
      Response.json({
        authenticated: false,
        customer: { email: "owner@example.com", roles: ["account_owner"] },
        source: "none",
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const response = await proxy(
      requestWithCookie(
        "/admin/matching-v2",
        `${CUSTOMER_SESSION_COOKIE_NAME}=${sessionCookie}; ${ADMIN_ROUTE_CACHE_COOKIE_NAME}=${customerCacheCookie}`,
      ),
    );

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "https://app.cpghero.com/admin/login?return_to=%2Fadmin%2Fmatching-v2",
    );
  });

  it("allows admin API routes when the customer session has system admin access", async () => {
    vi.stubEnv("PRODUCT_PACK_SESSION_SECRET", routeSecret);
    const fetchSpy = vi.fn().mockResolvedValue(
      Response.json({
        authenticated: true,
        source: "customer_system",
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const response = await proxy(
      requestWithCookie(
        "/api/admin/matching-v2/review-queues",
        `${CUSTOMER_SESSION_COOKIE_NAME}=${sessionCookie}`,
      ),
    );

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(String(fetchSpy.mock.calls[0]?.[0])).toBe(
      "https://app.cpghero.com/api/admin/session",
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });

  it("redirects admin pages when the customer session is not a system admin", async () => {
    vi.stubEnv("PRODUCT_PACK_SESSION_SECRET", routeSecret);
    const fetchSpy = vi.fn().mockResolvedValue(
      Response.json({
        authenticated: false,
        customer: { email: "owner@example.com", roles: ["account_owner"] },
        source: "none",
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const response = await proxy(
      requestWithCookie(
        "/admin/matching-v2",
        `${CUSTOMER_SESSION_COOKIE_NAME}=${sessionCookie}`,
      ),
    );

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "https://app.cpghero.com/admin/login?return_to=%2Fadmin%2Fmatching-v2",
    );
  });

  it("returns admin JSON 401 when the customer session is not a system admin", async () => {
    vi.stubEnv("PRODUCT_PACK_SESSION_SECRET", routeSecret);
    const fetchSpy = vi.fn().mockResolvedValue(
      Response.json({
        authenticated: false,
        customer: { email: "owner@example.com", roles: ["account_owner"] },
        source: "none",
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const response = await proxy(
      requestWithCookie(
        "/api/admin/matching-v2/review-queues",
        `${CUSTOMER_SESSION_COOKIE_NAME}=${sessionCookie}`,
      ),
    );

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(response.status).toBe(401);
    expect(response.headers.get("location")).toBeNull();
    expect(await response.json()).toEqual({
      error: "Administrator authentication is required.",
    });
  });
});
