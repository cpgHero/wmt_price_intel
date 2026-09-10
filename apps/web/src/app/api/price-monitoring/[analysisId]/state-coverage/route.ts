import { NextResponse } from "next/server";

import { postApiJson, type JsonObject } from "@/lib/api";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ analysisId: string }> },
) {
  const { analysisId } = await params;
  const body = (await request.json()) as JsonObject;
  const response = await postApiJson<JsonObject>(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/price-monitoring/state-coverage`,
    body,
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
    headers: {
      "Cache-Control": "private, no-store",
    },
  });
}
