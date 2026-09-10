import { NextResponse } from "next/server";

import { getApi } from "@/lib/api";
import { loadCanonicalReportDatasetResponse } from "@/lib/canonical-report-dataset-route";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ analysisId: string }> },
) {
  const { analysisId } = await params;
  const response = await loadCanonicalReportDatasetResponse(analysisId, getApi);
  return NextResponse.json(response.body, {
    status: response.status,
    headers: response.headers,
  });
}
