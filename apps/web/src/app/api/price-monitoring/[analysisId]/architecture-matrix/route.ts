import { NextResponse } from "next/server";

import { getApi, type PriceArchitectureMatrix } from "@/lib/api";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ analysisId: string }> },
) {
  const { analysisId } = await params;
  const query = new URL(request.url).searchParams.toString();
  const response = await getApi<PriceArchitectureMatrix>(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/price-architecture-matrix?${query}`,
    180_000,
  );
  if (!response.data) {
    return NextResponse.json(
      { error: response.error },
      { status: response.status },
    );
  }
  return NextResponse.json(response.data, {
    headers: {
      // The API service owns revision-aware matrix caching. Browser/proxy caching
      // can otherwise retain an obsolete matrix after a deploy or governance edit.
      "Cache-Control": "private, no-store",
    },
  });
}
