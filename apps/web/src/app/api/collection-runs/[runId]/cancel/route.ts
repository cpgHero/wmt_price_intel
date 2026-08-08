import { NextResponse } from "next/server";

import { postApi, type RunRecord } from "@/lib/api";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ runId: string }> },
) {
  const { runId } = await params;
  const response = await postApi<RunRecord>(
    `/api/v1/collection-runs/${encodeURIComponent(runId)}/cancel`,
  );
  if (!response.data)
    return NextResponse.json(
      { error: response.error },
      { status: response.status },
    );
  return NextResponse.json(response.data);
}
