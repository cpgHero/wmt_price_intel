import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CUSTOMER_ROUTE_CACHE_COOKIE_NAME,
  verifyCustomerRouteCacheCookie,
} from "../../../../lib/route-auth-cache";
import { CUSTOMER_SESSION_COOKIE_NAME } from "../../../../lib/route-access-policy";

import { GET } from "./route";

const routeSecret = "unit-route-cache-secret";

function routeCacheFromSetCookie(setCookie: string | null): string {
  const match = setCookie?.match(
    new RegExp(`${CUSTOMER_ROUTE_CACHE_COOKIE_NAME}=([^;]+)`),
  );
  if (!match?.[1]) throw new Error("Missing route cache cookie");
  return match[1];
}

describe("/api/auth/me route", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("primes the route-auth cache after a successful customer session check", async () => {
    vi.stubEnv("RCI_API_INTERNAL_URL", "http://api.internal");
    vi.stubEnv("PRODUCT_PACK_SESSION_SECRET", routeSecret);
    const sessionCookie = "sealed-customer-session.with=padding";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({
        principal: { email: "brian@example.com" },
      }),
    );

    const response = await GET(
      new Request("https://app.cpghero.com/api/auth/me", {
        headers: {
          accept: "application/json",
          cookie: `${CUSTOMER_SESSION_COOKIE_NAME}="${sessionCookie}"`,
        },
      }),
    );

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://api.internal/api/v1/me");
    expect((init?.headers as Headers).get("cookie")).toBe(
      `${CUSTOMER_SESSION_COOKIE_NAME}="${sessionCookie}"`,
    );
    expect(response.status).toBe(200);
    const routeCacheCookie = routeCacheFromSetCookie(
      response.headers.get("set-cookie"),
    );
    await expect(
      verifyCustomerRouteCacheCookie(
        routeCacheCookie,
        sessionCookie,
        routeSecret,
      ),
    ).resolves.toBe(true);
  });

  it("does not prime the route-auth cache when the customer session check fails", async () => {
    vi.stubEnv("RCI_API_INTERNAL_URL", "http://api.internal");
    vi.stubEnv("PRODUCT_PACK_SESSION_SECRET", routeSecret);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json(
        { detail: "Customer authentication is required." },
        { status: 401 },
      ),
    );

    const response = await GET(
      new Request("https://app.cpghero.com/api/auth/me", {
        headers: {
          accept: "application/json",
          cookie: `${CUSTOMER_SESSION_COOKIE_NAME}=invalid`,
        },
      }),
    );

    expect(response.status).toBe(401);
    expect(response.headers.get("set-cookie")).toBeNull();
  });
});
