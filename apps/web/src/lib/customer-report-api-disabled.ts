import { NextResponse } from "next/server";

export function customerReportApiDisabledResponse(): NextResponse {
  return NextResponse.json(
    {
      error:
        "Customer report access is disabled while legacy reporting is restored.",
    },
    { status: 404, headers: { "cache-control": "private, no-store" } },
  );
}
