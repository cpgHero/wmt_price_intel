import { NextResponse } from "next/server";

import { getApi, type CollectionBuilderOptions } from "@/lib/api";

export async function GET() {
  const response = await getApi<CollectionBuilderOptions>(
    "/api/v1/collection-builder/options",
  );
  if (!response.data) {
    return NextResponse.json(
      { error: response.error },
      { status: response.status },
    );
  }
  return NextResponse.json(response.data);
}
