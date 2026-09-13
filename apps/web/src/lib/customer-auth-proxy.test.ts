import { afterEach, describe, expect, it, vi } from "vitest";

import { proxyCustomerAuthGet } from "./customer-auth-proxy";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("customer auth proxy", () => {
  it("forwards redirect location and set-cookie from the API", async () => {
    vi.stubEnv("RCI_API_INTERNAL_URL", "http://api.internal");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(null, {
        status: 307,
        headers: {
          location: "https://auth.workos.test/authorize",
          "set-cookie": "cph_customer_auth_flow=sealed; Path=/; HttpOnly",
        },
      }),
    );

    const response = await proxyCustomerAuthGet(
      new Request("https://app.cpghero.com/api/auth/login?return_to=/reports", {
        headers: {
          cookie: "existing=value",
          "user-agent": "vitest",
        },
      }),
      "/api/auth/login",
    );

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(
      "http://api.internal/api/auth/login?return_to=/reports",
    );
    expect((init?.headers as Headers).get("cookie")).toBe("existing=value");
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "https://auth.workos.test/authorize",
    );
    expect(response.headers.get("set-cookie")).toContain(
      "cph_customer_auth_flow=sealed",
    );
    expect(response.headers.get("cache-control")).toBe("private, no-store");
  });

  it("returns a private no-store outage response when the API cannot be reached", async () => {
    vi.stubEnv("RCI_API_INTERNAL_URL", "http://api.internal");
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));

    const response = await proxyCustomerAuthGet(
      new Request("https://app.cpghero.com/api/auth/me"),
      "/api/v1/me",
    );

    expect(response.status).toBe(503);
    expect(response.headers.get("cache-control")).toBe("private, no-store");
    expect(await response.json()).toEqual({
      error: "The customer-auth API is not currently reachable.",
    });
  });
});
