import { afterEach, describe, expect, it, vi } from "vitest";

import {
  proxyCustomerAuthGet,
  proxyCustomerAuthWebhookPost,
} from "./customer-auth-proxy";

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

  it("preserves multiple callback set-cookie headers when the runtime combines them", async () => {
    vi.stubEnv("RCI_API_INTERNAL_URL", "http://api.internal");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(null, {
        status: 303,
        headers: {
          location: "/customer",
          "set-cookie":
            'cph_customer_session=sealed-session; Max-Age=28800; Path=/; HttpOnly; SameSite=lax, cph_customer_auth_flow=""; expires=Mon, 14 Sep 2026 21:51:00 GMT; Max-Age=0; Path=/; SameSite=lax',
        },
      }),
    );

    const response = await proxyCustomerAuthGet(
      new Request(
        "https://app.cpghero.com/api/auth/callback?code=abc&state=state",
        {
          headers: {
            accept: "text/html",
            cookie: "cph_customer_auth_flow=flow",
          },
        },
      ),
      "/api/auth/callback",
    );

    const readable = response.headers as Headers & {
      getSetCookie?: () => string[];
    };
    const setCookies = readable.getSetCookie?.() ?? [
      response.headers.get("set-cookie") ?? "",
    ];

    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe("/customer");
    expect(setCookies).toHaveLength(2);
    expect(setCookies[0]).toContain("cph_customer_session=sealed-session");
    expect(setCookies[1]).toContain("cph_customer_auth_flow=");
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

  it("renders browser navigation auth failures as a CPGHero page instead of raw JSON", async () => {
    vi.stubEnv("RCI_API_INTERNAL_URL", "http://api.internal");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json(
        { detail: "Customer authentication is disabled." },
        { status: 404 },
      ),
    );

    const response = await proxyCustomerAuthGet(
      new Request("https://app.cpghero.com/api/auth/callback?code=abc", {
        headers: { accept: "text/html,application/xhtml+xml" },
      }),
      "/api/auth/callback",
    );

    expect(response.status).toBe(404);
    expect(response.headers.get("content-type")).toBe(
      "text/html; charset=utf-8",
    );
    const html = await response.text();
    expect(html).toContain("CPGHero customer access");
    expect(html).toContain("Customer authentication is disabled.");
  });

  it("masks identity-provider names in browser auth failures", async () => {
    vi.stubEnv("RCI_API_INTERNAL_URL", "http://api.internal");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json(
        {
          detail:
            "WorkOS authentication response did not include a usable user.",
        },
        { status: 401 },
      ),
    );

    const response = await proxyCustomerAuthGet(
      new Request("https://app.cpghero.com/api/auth/callback?code=abc", {
        headers: { accept: "text/html" },
      }),
      "/api/auth/callback",
    );

    const html = await response.text();
    expect(html).toContain("CPGHero identity authentication response");
    expect(html).not.toContain("WorkOS");
  });

  it("keeps JSON auth failures as JSON for programmatic callers", async () => {
    vi.stubEnv("RCI_API_INTERNAL_URL", "http://api.internal");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json(
        { detail: "Customer authentication is required." },
        { status: 401 },
      ),
    );

    const response = await proxyCustomerAuthGet(
      new Request("https://app.cpghero.com/api/auth/me", {
        headers: { accept: "application/json" },
      }),
      "/api/v1/me",
    );

    expect(response.status).toBe(401);
    expect(response.headers.get("content-type")).toContain("application/json");
    expect(await response.json()).toEqual({
      detail: "Customer authentication is required.",
    });
  });

  it("forwards the raw WorkOS webhook body and signature to the API", async () => {
    vi.stubEnv("RCI_API_INTERNAL_URL", "http://api.internal");
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        Response.json({ status: "received" }, { status: 202 }),
      );
    const rawPayload = '{"id":"event_123","event":"user.created"}';

    const response = await proxyCustomerAuthWebhookPost(
      new Request("https://app.cpghero.com/api/webhooks/workos", {
        method: "POST",
        body: rawPayload,
        headers: {
          cookie: "customer=session",
          "content-type": "application/json",
          "user-agent": "workos-webhooks",
          "workos-signature": "t=1,v1=signature",
          authorization: "Bearer should-not-forward",
        },
      }),
      "/api/webhooks/workos",
    );

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    const forwardedHeaders = init?.headers as Headers;
    expect(String(url)).toBe("http://api.internal/api/webhooks/workos");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(rawPayload);
    expect(forwardedHeaders.get("content-type")).toBe("application/json");
    expect(forwardedHeaders.get("workos-signature")).toBe("t=1,v1=signature");
    expect(forwardedHeaders.get("cookie")).toBeNull();
    expect(forwardedHeaders.get("authorization")).toBeNull();
    expect(response.status).toBe(202);
    expect(response.headers.get("cache-control")).toBe("private, no-store");
    expect(await response.json()).toEqual({ status: "received" });
  });

  it("returns a private no-store outage response when the webhook API cannot be reached", async () => {
    vi.stubEnv("RCI_API_INTERNAL_URL", "http://api.internal");
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));

    const response = await proxyCustomerAuthWebhookPost(
      new Request("https://app.cpghero.com/api/webhooks/workos", {
        method: "POST",
        body: "{}",
        headers: { "workos-signature": "t=1,v1=signature" },
      }),
      "/api/webhooks/workos",
    );

    expect(response.status).toBe(503);
    expect(response.headers.get("cache-control")).toBe("private, no-store");
    expect(await response.json()).toEqual({
      error: "The customer-auth webhook API is not currently reachable.",
    });
  });
});
