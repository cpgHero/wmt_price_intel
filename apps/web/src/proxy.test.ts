import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { proxy } from "./proxy";

describe("proxy legacy restore mode", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not route app pages through customer authentication", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const response = proxy(new NextRequest("https://app.cpghero.com/proximity"));

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });

  it("does not route admin pages through WorkOS customer authentication", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const response = proxy(
      new NextRequest("https://app.cpghero.com/admin/matching-v2"),
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });

  it("leaves API authorization to the route handlers", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const response = proxy(
      new NextRequest(
        "https://app.cpghero.com/api/admin/matching-v2/review-queues",
      ),
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });

  it("redirects dormant customer pages to legacy destinations without auth checks", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const customerResponse = proxy(
      new NextRequest("https://app.cpghero.com/customer"),
    );
    const reportResponse = proxy(
      new NextRequest("https://app.cpghero.com/customer/reports/access-123"),
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(customerResponse.status).toBe(307);
    expect(customerResponse.headers.get("location")).toBe(
      "https://app.cpghero.com/",
    );
    expect(reportResponse.status).toBe(307);
    expect(reportResponse.headers.get("location")).toBe(
      "https://app.cpghero.com/analyses",
    );
  });
});
