import { NextResponse } from "next/server";

import { getApi, type LocationRetailer } from "@/lib/api";

export async function GET(request: Request) {
  const input = new URL(request.url);
  const parameters = new URLSearchParams();
  const country = input.searchParams.get("country");
  if (country) parameters.set("country", country);
  const response = await getApi<LocationRetailer[]>(
    `/api/v1/retailers?${parameters.toString()}`,
  );
  if (!response.data) {
    return NextResponse.json(
      { error: response.error },
      { status: response.status },
    );
  }
  return NextResponse.json(response.data, {
    headers: { "Cache-Control": "private, no-store" },
  });
}
