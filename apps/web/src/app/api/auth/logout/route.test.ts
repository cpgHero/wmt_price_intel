import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ADMIN_ROUTE_CACHE_COOKIE_NAME,
  CUSTOMER_ROUTE_CACHE_COOKIE_NAME,
} from "../../../../lib/route-auth-cache";

import { GET } from "./route";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("customer auth logout route", () => {
  it("does not forward logout to WorkOS in legacy restore mode", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    const response = GET(
      new Request("https://app.cpghero.com/api/auth/logout?return_to=/", {
        headers: {
          accept: "text/html",
          cookie: "cph_customer_session=sealed",
        },
      }),
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("https://app.cpghero.com/");
    expect(response.headers.get("set-cookie")).toContain(
      `${CUSTOMER_ROUTE_CACHE_COOKIE_NAME}=`,
    );
    expect(response.headers.get("set-cookie")).toContain(
      `${ADMIN_ROUTE_CACHE_COOKIE_NAME}=`,
    );
    expect(response.headers.get("set-cookie")).toContain("Max-Age=0");
  });

  it("uses the forwarded public origin when Railway supplies an internal request URL", () => {
    const response = GET(
      new Request("http://0.0.0.0:3000/api/auth/logout", {
        headers: {
          host: "0.0.0.0:3000",
          "x-forwarded-host": "web-production-ee2a4.up.railway.app",
          "x-forwarded-proto": "https",
        },
      }),
    );

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "https://web-production-ee2a4.up.railway.app/",
    );
  });
});
