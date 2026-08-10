import { NextResponse } from "next/server";

import { getApi, type ProductEvidenceResponse } from "@/lib/api";
import {
  productEvidenceCsv,
  productEvidenceFilename,
} from "@/lib/evidence-csv";

export async function GET(
  request: Request,
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
  if (new URL(request.url).searchParams.get("format") === "csv") {
    return new Response(productEvidenceCsv(result.data), {
      headers: {
        "Cache-Control": "private, no-store",
        "Content-Disposition": `attachment; filename="${productEvidenceFilename(result.data)}"`,
        "Content-Type": "text/csv; charset=utf-8",
      },
    });
  }
  return NextResponse.json(result.data);
}
