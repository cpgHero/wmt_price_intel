import { NextResponse } from "next/server";

import { getApi, type BrandWorkbench } from "@/lib/api";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ analysisId: string }> },
) {
  const { analysisId } = await params;
  const response = await getApi<BrandWorkbench>(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/brand-workbench`,
  );
  if (!response.data)
    return NextResponse.json(
      { error: response.error },
      { status: response.status },
    );
  return NextResponse.json(response.data);
}
