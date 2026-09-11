import { NextResponse } from "next/server";

import { getApi, type ProximityView } from "@/lib/api";

export async function GET(request: Request) {
  const input = new URL(request.url);
  const parameters = new URLSearchParams();
  for (const key of [
    "country",
    "benchmark_retailer_id",
    "competitor_retailer_id",
    "selected_radius_miles",
  ]) {
    const value = input.searchParams.get(key);
    if (value) parameters.set(key, value);
  }
  const response = await getApi<ProximityView>(
    `/api/v1/proximity?${parameters.toString()}`,
    120_000,
  );
  if (!response.data) {
    return NextResponse.json(
      { error: response.error },
      {
        status: response.status,
        headers: { "Cache-Control": "private, no-store" },
      },
    );
  }
  return NextResponse.json(response.data, {
    headers: { "Cache-Control": "private, no-store" },
  });
}
