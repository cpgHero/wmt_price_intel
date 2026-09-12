import { EmptyState } from "@/app/components/empty-state";
import { getApi, type LocationRetailer, type ProximityView } from "@/lib/api";

import { ProximityWorkspace } from "./proximity-workspace";

export const dynamic = "force-dynamic";
const DEFAULT_RADIUS_MILES = 1;

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
  const value = Number(radius ?? DEFAULT_RADIUS_MILES);
  return Number.isFinite(value) && value > 0 ? value : DEFAULT_RADIUS_MILES;
}

function defaultCompetitor(retailers: LocationRetailer[], country: string) {
  const benchmark = walmartRetailerId(country);
  return (
    retailers
      .filter(
        (retailer) =>
          retailer.country === country &&
          retailer.id !== benchmark &&
          !retailer.id.startsWith("walmart_") &&
          retailer.location_count > 0,
      )
      .sort(
        (left, right) =>
          Number(right.active) - Number(left.active) ||
          Number(right.catalogued) - Number(left.catalogued) ||
          right.location_count - left.location_count ||
          left.display_name.localeCompare(right.display_name),
      )[0]?.id ?? null
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
