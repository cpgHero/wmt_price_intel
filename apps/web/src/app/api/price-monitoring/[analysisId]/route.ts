import { NextResponse } from "next/server";

import { getApi, type PriceMonitoringView } from "@/lib/api";
import { compactPriceMonitoringCatalog } from "@/lib/price-monitoring-catalog";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ analysisId: string }> },
) {
  const { analysisId } = await params;
  const query = new URL(request.url).searchParams.toString();
  const response = await getApi<PriceMonitoringView>(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/price-monitoring?${query}`,
    120_000,
  );
  if (!response.data) {
    return NextResponse.json(
      { error: response.error },
      { status: response.status },
    );
  }
  return NextResponse.json(compactPriceMonitoringCatalog(response.data), {
    headers: {
      "Cache-Control": "private, max-age=60, stale-while-revalidate=300",
    },
  });
}
