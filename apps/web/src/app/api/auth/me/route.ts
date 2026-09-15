export const dynamic = "force-dynamic";

export function GET() {
  return Response.json(
    { error: "Customer authentication is disabled." },
    { status: 401, headers: { "cache-control": "private, no-store" } },
  );
}
