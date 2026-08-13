import { loadServerConfig } from "@/lib/config";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ analysisId: string }> },
) {
  const { analysisId } = await params;
  const query = new URL(request.url).searchParams.toString();
  const { apiInternalUrl } = loadServerConfig();
  try {
    const upstream = await fetch(
      new URL(
        `/api/v1/analyses/${encodeURIComponent(analysisId)}/price-monitoring/evidence.csv?${query}`,
        apiInternalUrl,
      ),
      {
        cache: "no-store",
        signal: AbortSignal.timeout(120_000),
      },
    );
    const body = await upstream.arrayBuffer();
    return new Response(body, {
      status: upstream.status,
      headers: {
        "content-type":
          upstream.headers.get("content-type") ?? "text/csv; charset=utf-8",
        "content-disposition":
          upstream.headers.get("content-disposition") ??
          'attachment; filename="price-evidence.csv"',
      },
    });
  } catch {
    return Response.json(
      { error: "The evidence export is temporarily unavailable." },
      { status: 503 },
    );
  }
}
