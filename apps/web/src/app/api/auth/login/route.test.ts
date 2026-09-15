import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("customer auth login route", () => {
  it("does not start a hosted login flow in legacy restore mode", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    const response = GET(
      new Request(
        "https://app.cpghero.com/api/auth/login?return_to=/customer",
        {
          headers: { accept: "text/html" },
        },
      ),
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("https://app.cpghero.com/");
  });

  it("also redirects stale background login attempts to the restored app home", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    const response = GET(
      new Request("https://app.cpghero.com/api/auth/login?_rsc=abc123", {
        headers: { rsc: "1" },
      }),
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("https://app.cpghero.com/");
  });
});
