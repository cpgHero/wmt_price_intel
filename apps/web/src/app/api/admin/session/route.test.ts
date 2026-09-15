import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("../../../../lib/admin-access", () => ({
  adminSessionStatus: vi.fn(),
}));

import { adminSessionStatus } from "../../../../lib/admin-access";

import { GET } from "./route";

const adminSessionStatusMock = vi.mocked(adminSessionStatus);

describe("/api/admin/session route", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns the legacy admin session status without issuing WorkOS route caches", () => {
    adminSessionStatusMock.mockReturnValue({
      authenticated: true,
      configured: true,
      source: "legacy_admin",
    });

    const response = GET(
      new Request("https://app.cpghero.com/api/admin/session"),
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("private, no-store");
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it("returns unauthenticated legacy status without issuing cookies", () => {
    adminSessionStatusMock.mockReturnValue({
      authenticated: false,
      configured: true,
      source: "none",
    });

    const response = GET(
      new Request("https://app.cpghero.com/api/admin/session"),
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("set-cookie")).toBeNull();
  });
});
