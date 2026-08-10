import { NextResponse } from "next/server";

import { getApi, type ProductEvidenceResponse } from "@/lib/api";

export async function GET(
  _request: Request,
  {
    params,
  }: {
    params: Promise<{ analysisId: string; decisionId: string }>;
  },
) {
  const { analysisId, decisionId } = await params;
  const result = await getApi<ProductEvidenceResponse>(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/product-decisions/${encodeURIComponent(decisionId)}/evidence`,
  );
  if (!result.data) {
    return NextResponse.json(
      { error: result.error ?? "Product evidence is unavailable." },
      { status: result.status },
    );
  }
  return NextResponse.json(result.data);
}
