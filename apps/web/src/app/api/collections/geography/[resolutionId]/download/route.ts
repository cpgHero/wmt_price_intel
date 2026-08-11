import { NextResponse } from "next/server";

import { loadServerConfig } from "@/lib/config";

export async function GET(
  _request: Request,
  context: { params: Promise<{ resolutionId: string }> },
) {
  const { resolutionId } = await context.params;
  const { apiInternalUrl } = loadServerConfig();
  try {
    const response = await fetch(
      new URL(
        `/api/v1/collection-geography-resolutions/${encodeURIComponent(resolutionId)}/download`,
        apiInternalUrl,
      ),
      { cache: "no-store", signal: AbortSignal.timeout(15_000) },
    );
    if (!response.ok) {
      return NextResponse.json(
        { error: `API returned ${response.status}` },
        { status: response.status },
      );
    }
    return new NextResponse(response.body, {
      headers: {
        "content-type": response.headers.get("content-type") ?? "text/csv",
        "content-disposition":
          response.headers.get("content-disposition") ??
          `attachment; filename="geography-${resolutionId}.csv"`,
      },
    });
  } catch {
    return NextResponse.json(
      { error: "The API is not currently reachable from the web service." },
      { status: 503 },
    );
  }
}
