import { NextResponse } from "next/server";

import { getApi, type MatchingV2ShadowView } from "@/lib/api";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ analysisId: string }> },
) {
  const { analysisId } = await params;
  const query = new URL(request.url).searchParams.toString();
  const response = await getApi<MatchingV2ShadowView>(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/matching-v2-shadow${query ? `?${query}` : ""}`,
  );
  if (!response.data)
    return NextResponse.json(
      { error: response.error },
      { status: response.status },
    );
  return NextResponse.json(response.data);
}
