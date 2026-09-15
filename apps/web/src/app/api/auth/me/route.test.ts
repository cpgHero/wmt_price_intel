import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

describe("/api/auth/me route", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fails closed without calling WorkOS-backed identity in legacy restore mode", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");

    const response = GET();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(response.status).toBe(401);
    expect(response.headers.get("cache-control")).toBe("private, no-store");
    expect(response.headers.get("set-cookie")).toBeNull();
    await expect(response.json()).resolves.toEqual({
      error: "Customer authentication is disabled.",
    });
  });
});
