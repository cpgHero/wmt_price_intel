import { NextResponse } from "next/server";

import { postApi, type JsonObject } from "@/lib/api";

interface ArtifactRecord extends JsonObject {
  id: string;
}
interface DownloadRecord extends JsonObject {
  url: string;
}

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ analysisId: string; artifactType: string }> },
) {
  const { analysisId, artifactType } = await params;
  const allowed = new Set(["html", "xlsx", "leadership_email", "audit_zip"]);
  if (!allowed.has(artifactType))
    return NextResponse.json(
      { error: "Unsupported artifact type." },
      { status: 400 },
    );
  const artifact = await postApi<ArtifactRecord>(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/artifacts/${artifactType}`,
  );
  if (!artifact.data)
    return NextResponse.json(
      { error: artifact.error },
      { status: artifact.status },
    );
  const download = await import("@/lib/api").then(({ getApi }) =>
    getApi<DownloadRecord>(
      `/api/v1/artifacts/${encodeURIComponent(artifact.data!.id)}/download`,
    ),
  );
  if (!download.data)
    return NextResponse.json(
      { error: download.error },
      { status: download.status },
    );
  return NextResponse.json({
    artifact: artifact.data,
    download_url: download.data.url,
  });
}
