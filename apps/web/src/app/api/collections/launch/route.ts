import { NextResponse } from "next/server";

import { postApiJson, type JsonObject, type RunRecord } from "@/lib/api";

export async function POST(request: Request) {
  const body = (await request.json()) as JsonObject;
  const launched = await postApiJson<RunRecord>(
    "/api/v1/collection-launches",
    body,
  );
  if (!launched.data) {
    return NextResponse.json(
      { error: launched.error },
      { status: launched.status },
    );
  }
  return NextResponse.json(launched.data, { status: 201 });
}
