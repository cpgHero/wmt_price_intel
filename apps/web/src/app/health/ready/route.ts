import { loadServerConfig } from "@/lib/config";

export async function GET() {
  const { apiInternalUrl } = loadServerConfig();
  try {
    const response = await fetch(new URL("/health/ready", apiInternalUrl), {
      cache: "no-store",
      signal: AbortSignal.timeout(2_000),
    });
    return Response.json(
      {
        status: response.ok ? "ready" : "not_ready",
        service: "web",
        dependencies: { api: response.ok ? "ok" : "unavailable" },
      },
      { status: response.ok ? 200 : 503 },
    );
  } catch {
    return Response.json(
      {
        status: "not_ready",
        service: "web",
        dependencies: { api: "unavailable" },
      },
      { status: 503 },
    );
  }
}
