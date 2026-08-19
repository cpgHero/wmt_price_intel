import type { CompetitiveProductLeadership } from "./api";

export interface CompetitiveProductLeadershipRequest {
  analysisId: string;
  competitorId: string;
  profileId: string;
  productId: string;
  radiusMiles: 1 | 3 | 5;
  stateFilter?: string | null;
  cityFilter?: string | null;
}

const completed = new Map<string, CompetitiveProductLeadership>();
const pending = new Map<string, Promise<CompetitiveProductLeadership>>();

export function competitiveProductLeadershipPath(
  request: CompetitiveProductLeadershipRequest,
) {
  const parameters = new URLSearchParams({
    competitor: request.competitorId,
    profile: request.profileId,
    product: request.productId,
    radius_miles: String(request.radiusMiles),
  });
  if (request.stateFilter) parameters.set("state", request.stateFilter);
  if (request.stateFilter && request.cityFilter)
    parameters.set("city", request.cityFilter);
  return `/api/analyses/${encodeURIComponent(request.analysisId)}/competitive-product-leadership?${parameters}`;
}

export async function loadCompetitiveProductLeadership(
  request: CompetitiveProductLeadershipRequest,
) {
  const path = competitiveProductLeadershipPath(request);
  const cached = completed.get(path);
  if (cached) return cached;
  const inFlight = pending.get(path);
  if (inFlight) return inFlight;

  const promise = fetch(path, { cache: "no-store" })
    .then(async (response) => {
      const body = (await response.json()) as CompetitiveProductLeadership & {
        error?: string;
      };
      if (!response.ok)
        throw new Error(
          body.error || `Leadership evidence returned ${response.status}`,
        );
      if (completed.size >= 16)
        completed.delete(completed.keys().next().value!);
      completed.set(path, body);
      return body;
    })
    .finally(() => pending.delete(path));
  pending.set(path, promise);
  return promise;
}

export function prewarmCompetitiveProductLeadership(
  request: CompetitiveProductLeadershipRequest,
) {
  void loadCompetitiveProductLeadership(request).catch(() => undefined);
}
