import { afterEach, describe, expect, it, vi } from "vitest";

import { assertSameOrigin, publicRequestOrigin } from "./request-origin";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("publicRequestOrigin", () => {
  it("prefers Railway forwarded HTTPS host over the internal request URL", () => {
    const request = new Request("http://0.0.0.0:3000/api/auth/login", {
      headers: {
        host: "0.0.0.0:3000",
        "x-forwarded-host": "web-production-ee2a4.up.railway.app",
        "x-forwarded-proto": "https",
      },
    });

    expect(publicRequestOrigin(request)).toBe(
      "https://web-production-ee2a4.up.railway.app",
    );
  });

  it("falls back to the request origin when no usable public host is supplied", () => {
    const request = new Request("https://app.cpghero.com/api/auth/login");

    expect(publicRequestOrigin(request)).toBe("https://app.cpghero.com");
  });
});

describe("assertSameOrigin", () => {
  it("accepts a direct same-origin request", () => {
    const request = new Request("https://app.example.com/api/admin/session", {
      headers: { origin: "https://app.example.com" },
    });
    expect(assertSameOrigin(request)).toBe(true);
  });

  it("accepts Railway's public HTTPS origin for an internal request URL", () => {
    vi.stubEnv("RAILWAY_PUBLIC_DOMAIN", "app.example.com");
    const request = new Request(
      "http://web.railway.internal/api/admin/session",
      {
        headers: { origin: "https://app.example.com" },
      },
    );
    expect(assertSameOrigin(request)).toBe(true);
  });

  it("accepts exact proxy-forwarded host and protocol", () => {
    const request = new Request(
      "http://web.railway.internal/api/admin/session",
      {
        headers: {
          origin: "https://app.example.com",
          "x-forwarded-host": "app.example.com",
          "x-forwarded-proto": "https",
        },
      },
    );
    expect(assertSameOrigin(request)).toBe(true);
  });

  it("accepts an explicitly configured custom origin", () => {
    vi.stubEnv(
      "PRODUCT_PACK_ALLOWED_ORIGINS",
      "https://admin.example.com, https://other.example.com",
    );
    const request = new Request(
      "http://web.railway.internal/api/admin/session",
      {
        headers: { origin: "https://admin.example.com" },
      },
    );
    expect(assertSameOrigin(request)).toBe(true);
  });

  it("rejects a different or malformed origin", () => {
    vi.stubEnv("RAILWAY_PUBLIC_DOMAIN", "app.example.com");
    expect(
      assertSameOrigin(
        new Request("http://web.railway.internal/api/admin/session", {
          headers: { origin: "https://attacker.example" },
        }),
      ),
    ).toBe(false);
    expect(
      assertSameOrigin(
        new Request("http://web.railway.internal/api/admin/session", {
          headers: { origin: "not a URL" },
        }),
      ),
    ).toBe(false);
  });

  it("allows server-to-server requests without an Origin header", () => {
    expect(
      assertSameOrigin(
        new Request("http://web.railway.internal/api/admin/session"),
      ),
    ).toBe(true);
  });
});
