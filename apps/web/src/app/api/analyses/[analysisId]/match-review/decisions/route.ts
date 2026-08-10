import { NextResponse } from "next/server";

import { postApiJson, type JsonObject } from "@/lib/api";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ analysisId: string }> },
) {
  const { analysisId } = await params;
  const body = (await request.json()) as JsonObject;
  const response = await postApiJson<JsonObject>(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/match-review/decisions`,
    body,
  );
  if (!response.data)
    return NextResponse.json(
      { error: response.error },
      { status: response.status },
    );
  return NextResponse.json(response.data);
}
