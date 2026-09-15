import { afterEach, describe, expect, it, vi } from "vitest";

import { CUSTOMER_ROUTE_CACHE_COOKIE_NAME } from "../../../../lib/route-auth-cache";

import { GET } from "./route";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("customer auth logout route", () => {
  it("clears the customer route-auth cache while forwarding logout", async () => {
    vi.stubEnv("RCI_API_INTERNAL_URL", "http://api.internal");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(null, {
        status: 303,
        headers: {
          location: "/",
          "set-cookie": "cph_customer_session=; Max-Age=0; Path=/; HttpOnly",
        },
      }),
    );

    const response = await GET(
      new Request("https://app.cpghero.com/api/auth/logout?return_to=/", {
        headers: { cookie: "cph_customer_session=sealed" },
      }),
    );

    expect(fetchSpy).toHaveBeenCalledOnce();
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe("/");
    expect(response.headers.get("set-cookie")).toContain(
      `${CUSTOMER_ROUTE_CACHE_COOKIE_NAME}=`,
    );
    expect(response.headers.get("set-cookie")).toContain("Max-Age=0");
  });
});
