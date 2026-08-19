import { notFound } from "next/navigation";

import { EmptyState } from "@/app/components/empty-state";
import {
  getApi,
  type AnalysisRecord,
  type PriceMonitoringView,
} from "@/lib/api";

import { PriceMonitoringWorkspace } from "./workspace";

export const dynamic = "force-dynamic";

interface PriceSearchParams {
  retailer?: string;
  brand_type?: string;
  state?: string;
  city?: string;
  zipcode?: string;
  product_id?: string;
  tab?: string;
}

export default async function PriceMonitoringDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ analysisId: string }>;
  searchParams: Promise<PriceSearchParams>;
}) {
  const [{ analysisId }, query] = await Promise.all([params, searchParams]);
  const analysisResponse = await getApi<AnalysisRecord>(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}`,
  );
  if (analysisResponse.status === 404) notFound();
  if (!analysisResponse.data) {
    return (
      <main>
        <EmptyState
          eyebrow="Price view unavailable"
          title="The analysis could not be loaded"
          message={
            analysisResponse.error ?? "Try again when the API is available."
          }
        />
      </main>
    );
  }
  const result = analysisResponse.data.result;
  const defaultRetailer = String(
    query.retailer ??
      ("benchmark_retailer" in result
        ? result.benchmark_retailer
        : "walmart_us"),
  );
  const request = new URLSearchParams({ retailer: defaultRetailer });
  for (const key of [
    "brand_type",
    "state",
    "city",
    "zipcode",
    "product_id",
  ] as const) {
    if (query[key]) request.set(key, String(query[key]));
  }
  const viewResponse = await getApi<PriceMonitoringView>(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/price-monitoring?${request.toString()}`,
    120_000,
  );
  if (!viewResponse.data) {
    return (
      <main>
        <EmptyState
          eyebrow="Search evidence unavailable"
          title="This price view cannot be assembled yet"
          message={
            viewResponse.error ?? "No classified Search evidence was found."
          }
        />
      </main>
    );
  }
  return (
    <main className="price-monitoring-page">
      <PriceMonitoringWorkspace
        initialTab={query.tab}
        initialView={viewResponse.data}
      />
    </main>
  );
}
