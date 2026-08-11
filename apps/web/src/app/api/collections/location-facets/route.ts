import { NextResponse } from "next/server";

import { getApi, type CollectionLocationFacet } from "@/lib/api";

export async function GET(request: Request) {
  const input = new URL(request.url);
  const parameters = new URLSearchParams();
  for (const key of ["retailer_id", "country", "states"]) {
    for (const value of input.searchParams.getAll(key)) {
      parameters.append(key, value);
    }
  }
  const response = await getApi<CollectionLocationFacet[]>(
    `/api/v1/collection-builder/location-facets?${parameters.toString()}`,
  );
  if (!response.data) {
    return NextResponse.json(
      { error: response.error },
      { status: response.status },
    );
  }
  return NextResponse.json(response.data);
}
