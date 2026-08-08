import { NextResponse } from "next/server";

import { postApiJson, type JsonObject, type RunRecord } from "@/lib/api";

interface DefinitionResponse {
  stable_key: string;
}

export async function POST(request: Request) {
  const config = (await request.json()) as JsonObject;
  const published = await postApiJson<DefinitionResponse>(
    "/api/v1/collection-definitions",
    config,
  );
  if (!published.data) {
    return NextResponse.json(
      { error: published.error },
      { status: published.status },
    );
  }
  const launched = await postApiJson<RunRecord>(
    `/api/v1/collection-definitions/${encodeURIComponent(published.data.stable_key)}/runs`,
  );
  if (!launched.data) {
    return NextResponse.json(
      { error: launched.error },
      { status: launched.status },
    );
  }
  return NextResponse.json(launched.data, { status: 201 });
}
