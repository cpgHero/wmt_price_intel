import { EmptyState } from "@/app/components/empty-state";
import { getApi, type LocationRetailer, type ProximityView } from "@/lib/api";

import { ProximityWorkspace } from "./proximity-workspace";

export const dynamic = "force-dynamic";

interface ProximitySearchParams {
  country?: string;
  competitor?: string;
  radius?: string;
}

function walmartRetailerId(country: string) {
  return country === "CANADA" ? "walmart_ca" : "walmart_us";
}

function normalizeCountry(country: string | undefined) {
  const normalized = (country ?? "USA").toUpperCase();
  if (normalized === "CA" || normalized === "CAN" || normalized === "CANADA") {
    return "CANADA";
  }
  return "USA";
}

function normalizeRadius(radius: string | undefined) {
  const value = Number(radius ?? 10);
  return Number.isFinite(value) && value > 0 ? value : 10;
}

function defaultCompetitor(retailers: LocationRetailer[], country: string) {
  const benchmark = walmartRetailerId(country);
  return (
    retailers.find(
      (retailer) =>
        retailer.country === country &&
        retailer.id !== benchmark &&
        !retailer.id.startsWith("walmart_") &&
        retailer.location_count > 0,
    )?.id ?? null
  );
}

export default async function ProximityPage({
  searchParams,
}: {
  searchParams: Promise<ProximitySearchParams>;
}) {
  const { country: countryParam, competitor, radius } = await searchParams;
  const country = normalizeCountry(countryParam);
  const radiusMiles = normalizeRadius(radius);
  const retailersResponse = await getApi<LocationRetailer[]>(
    `/api/v1/retailers?country=${encodeURIComponent(country)}`,
  );
  const retailers = retailersResponse.data ?? [];
  const competitorRetailerId =
    competitor ?? defaultCompetitor(retailers, country);
  const proximityResponse = competitorRetailerId
    ? await getApi<ProximityView>(
        `/api/v1/proximity?${new URLSearchParams({
          country,
          competitor_retailer_id: competitorRetailerId,
          selected_radius_miles: String(radiusMiles),
        }).toString()}`,
        120_000,
      )
    : { data: null, error: "No competitor retailer locations are available." };

  return (
    <main>
      <header className="page-header compact">
        <div>
          <p className="eyebrow">Analytics</p>
          <h1>Proximity</h1>
        </div>
        <p>
          Compare Walmart US or CA against one selected retailer using the
          location master. The page maps nearest-store relationships, radius
          coverage, and downloadable store-pair evidence.
        </p>
      </header>
      {retailersResponse.error ? (
        <EmptyState
          eyebrow="Location API unavailable"
          message={retailersResponse.error}
          title="Proximity could not load retailer locations"
        />
      ) : (
        <ProximityWorkspace
          initialCompetitorRetailerId={competitorRetailerId}
          initialCountry={country}
          initialRetailers={retailers}
          initialView={proximityResponse.data ?? null}
        />
      )}
    </main>
  );
}
