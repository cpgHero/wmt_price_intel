import { describe, expect, it } from "vitest";

import {
  CUSTOMER_ROUTE_CACHE_SECONDS,
  createCustomerRouteCacheCookie,
  verifyCustomerRouteCacheCookie,
} from "./route-auth-cache";

describe("customer route authentication cache", () => {
  it("creates a short-lived token bound to the current customer session cookie", async () => {
    const token = await createCustomerRouteCacheCookie(
      "sealed-session-cookie",
      "route-secret",
      100,
    );

    expect(token).toBeTruthy();
    await expect(
      verifyCustomerRouteCacheCookie(
        token,
        "sealed-session-cookie",
        "route-secret",
        100 + CUSTOMER_ROUTE_CACHE_SECONDS - 1,
      ),
    ).resolves.toBe(true);
  });

  it("rejects a token replayed with a different customer session cookie", async () => {
    const token = await createCustomerRouteCacheCookie(
      "sealed-session-cookie",
      "route-secret",
      100,
    );

    await expect(
      verifyCustomerRouteCacheCookie(
        token,
        "different-sealed-session-cookie",
        "route-secret",
        101,
      ),
    ).resolves.toBe(false);
  });

  it("rejects expired, malformed, and tampered tokens", async () => {
    const token = await createCustomerRouteCacheCookie(
      "sealed-session-cookie",
      "route-secret",
      100,
    );
    expect(token).toBeTruthy();

    await expect(
      verifyCustomerRouteCacheCookie(
        token,
        "sealed-session-cookie",
        "route-secret",
        100 + CUSTOMER_ROUTE_CACHE_SECONDS,
      ),
    ).resolves.toBe(false);
    await expect(
      verifyCustomerRouteCacheCookie(
        "not.a.valid.token.extra",
        "sealed-session-cookie",
        "route-secret",
        101,
      ),
    ).resolves.toBe(false);
    await expect(
      verifyCustomerRouteCacheCookie(
        `${token?.slice(0, -1)}x`,
        "sealed-session-cookie",
        "route-secret",
        101,
      ),
    ).resolves.toBe(false);
  });

  it("fails closed when required inputs are missing", async () => {
    await expect(
      createCustomerRouteCacheCookie("", "route-secret", 100),
    ).resolves.toBeNull();
    await expect(
      createCustomerRouteCacheCookie("sealed-session-cookie", "", 100),
    ).resolves.toBeNull();
    await expect(
      verifyCustomerRouteCacheCookie(
        "",
        "sealed-session-cookie",
        "route-secret",
        100,
      ),
    ).resolves.toBe(false);
    await expect(
      verifyCustomerRouteCacheCookie("token", "", "route-secret", 100),
    ).resolves.toBe(false);
    await expect(
      verifyCustomerRouteCacheCookie("token", "sealed-session-cookie", "", 100),
    ).resolves.toBe(false);
  });
});
