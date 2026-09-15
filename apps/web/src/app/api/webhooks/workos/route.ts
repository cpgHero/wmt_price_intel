export const dynamic = "force-dynamic";

export function POST() {
  return new Response(null, {
    status: 204,
    headers: { "cache-control": "private, no-store" },
  });
}
