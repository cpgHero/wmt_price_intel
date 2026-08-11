import { NextResponse } from "next/server";

import {
  postApiJson,
  type CollectionGeographyResolution,
  type JsonObject,
} from "@/lib/api";

export async function POST(request: Request) {
  const body = (await request.json()) as JsonObject;
  const response = await postApiJson<CollectionGeographyResolution>(
    "/api/v1/collection-geography-resolutions",
    body,
  );
  if (!response.data) {
    return NextResponse.json(
      { error: response.error },
      { status: response.status },
    );
  }
  return NextResponse.json(response.data, { status: 201 });
}
