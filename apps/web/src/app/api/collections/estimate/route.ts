import { NextResponse } from "next/server";

import { postApiJson, type CostEstimate, type JsonObject } from "@/lib/api";

export async function POST(request: Request) {
  const config = (await request.json()) as JsonObject;
  const response = await postApiJson<CostEstimate>(
    "/api/v1/collection-estimates",
    config,
  );
  if (!response.data) {
    return NextResponse.json(
      { error: response.error },
      { status: response.status },
    );
  }
  return NextResponse.json(response.data);
}
