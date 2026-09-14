import { NextResponse } from "next/server";

import type { AnalysisRecord, AnalysisReportView } from "@/lib/api";
import { canonicalReportDatasetFromReportView } from "@/lib/canonical-report-dataset";
import { canonicalReportIntegrityIssues } from "@/lib/canonical-report-qa";
import { loadServerConfig } from "@/lib/config";

export const dynamic = "force-dynamic";

interface CustomerReportViewResponse {
  analysis: AnalysisRecord;
  view: AnalysisReportView;
}

function upstreamHeaders(request: Request): Headers {
  const headers = new Headers({ accept: "application/json" });
  const cookie = request.headers.get("cookie");
  if (cookie) headers.set("cookie", cookie);
  const userAgent = request.headers.get("user-agent");
  if (userAgent) headers.set("user-agent", userAgent);
  return headers;
}

function errorResponse(error: string | null, status: number): NextResponse {
  return NextResponse.json(
    { error: error ?? "Canonical report dataset is unavailable." },
    { status, headers: { "cache-control": "private, no-store" } },
  );
}

export async function GET(
  request: Request,
  context: { params: Promise<{ accessId: string }> },
) {
  const { accessId } = await context.params;
  const upstreamUrl = new URL(
    `/api/v1/customer/reports/${encodeURIComponent(accessId)}/report`,
    loadServerConfig().apiInternalUrl,
  );
  try {
    const upstream = await fetch(upstreamUrl, {
      headers: upstreamHeaders(request),
      cache: "no-store",
      signal: AbortSignal.timeout(120_000),
    });
    const payload = (await upstream.json()) as
      CustomerReportViewResponse | { detail?: string; error?: string };
    if (!upstream.ok || !("analysis" in payload) || !("view" in payload)) {
      return errorResponse(
        "detail" in payload && typeof payload.detail === "string"
          ? payload.detail
          : "error" in payload && typeof payload.error === "string"
            ? payload.error
            : null,
        upstream.status,
      );
    }
    if (payload.analysis.schema_version !== "2.0.0") {
      return errorResponse(
        "Canonical report dataset preview requires an AnalysisResult v2 report.",
        409,
      );
    }
    const dataset = canonicalReportDatasetFromReportView(
      payload.analysis,
      payload.view,
    );
    const integrityIssues = canonicalReportIntegrityIssues(dataset);
    if (integrityIssues.length > 0) {
      return errorResponse(
        `Canonical report dataset failed integrity checks: ${integrityIssues
          .slice(0, 5)
          .map((issue) => issue.code)
          .join(", ")}`,
        422,
      );
    }
    return NextResponse.json(dataset, {
      headers: { "cache-control": "private, no-store" },
    });
  } catch {
    return errorResponse(
      "The customer canonical report dataset API is not currently reachable.",
      503,
    );
  }
}
