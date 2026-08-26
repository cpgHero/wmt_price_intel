import { NextResponse } from "next/server";

import { getApi } from "@/lib/api";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ analysisId: string }> },
) {
  const { analysisId } = await params;
  const query = new URL(request.url).searchParams.toString();
  const response = await getApi<Record<string, unknown>>(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/competitive-product-coverage?${query}`,
    120_000,
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
