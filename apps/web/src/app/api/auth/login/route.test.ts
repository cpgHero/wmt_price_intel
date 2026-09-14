import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("customer auth login route", () => {
  it("does not start hosted login for RSC background requests", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    const response = await GET(
      new Request("https://app.cpghero.com/api/auth/login?_rsc=abc123", {
        headers: { rsc: "1" },
      }),
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(response.status).toBe(401);
    expect(response.headers.get("cache-control")).toBe("private, no-store");
    expect(await response.json()).toEqual({
      error: "Customer authentication requires a browser navigation.",
    });
  });

  it("starts hosted login for a normal browser navigation", async () => {
    vi.stubEnv("RCI_API_INTERNAL_URL", "http://api.internal");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(null, {
        status: 307,
        headers: {
          location: "https://identity.example.test/authorize",
          "set-cookie": "cph_customer_auth_flow=sealed; Path=/; HttpOnly",
        },
      }),
    );

    const response = await GET(
      new Request(
        "https://app.cpghero.com/api/auth/login?return_to=/customer",
        {
          headers: { accept: "text/html" },
        },
      ),
    );

    expect(fetchSpy).toHaveBeenCalledOnce();
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "https://identity.example.test/authorize",
    );
  });
});
