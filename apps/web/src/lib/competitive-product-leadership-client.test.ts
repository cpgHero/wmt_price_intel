import { afterEach, describe, expect, it, vi } from "vitest";

import {
  competitiveProductLeadershipPath,
  loadCompetitiveProductLeadership,
} from "./competitive-product-leadership-client";

const request = {
  analysisId: "egg-report",
  competitorId: "target_us",
  profileId: "compatible",
  productId: "10449724",
  radiusMiles: 5 as const,
};

describe("competitive product leadership client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("builds one canonical request path for prewarm and visible views", () => {
    expect(
      competitiveProductLeadershipPath({
        analysisId: "egg report/1",
        competitorId: "target_us",
        profileId: "compatible",
        productId: "10449724",
        radiusMiles: 5,
        stateFilter: "TX",
        cityFilter: "Dallas",
      }),
    ).toBe(
      "/api/analyses/egg%20report%2F1/competitive-product-leadership?competitor=target_us&profile=compatible&product=10449724&radius_miles=5&state=TX&city=Dallas",
    );
  });

  it("never applies a city without its state", () => {
    expect(
      competitiveProductLeadershipPath({
        analysisId: "egg-report",
        competitorId: "all",
        profileId: "strict",
        productId: "391346672",
        radiusMiles: 3,
        cityFilter: "Bentonville",
      }),
    ).not.toContain("city=");
  });

  it("does not reuse completed leadership responses", async () => {
    const fetchMock = vi.fn(async () =>
      Promise.resolve(
        new Response(JSON.stringify({ schema_version: "1.3.0" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await loadCompetitiveProductLeadership(request);
    await loadCompetitiveProductLeadership(request);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenNthCalledWith(1, expect.any(String), {
      cache: "no-store",
    });
  });

  it("deduplicates only concurrent leadership requests", async () => {
    let resolveResponse!: (response: Response) => void;
    const fetchMock = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          resolveResponse = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const first = loadCompetitiveProductLeadership(request);
    const second = loadCompetitiveProductLeadership(request);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    resolveResponse(
      new Response(JSON.stringify({ schema_version: "1.3.0" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    await Promise.all([first, second]);
  });
});
