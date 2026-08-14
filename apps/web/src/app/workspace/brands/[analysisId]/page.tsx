import Link from "next/link";
import { notFound } from "next/navigation";

import { BrandWorkbenchPanel } from "@/app/analyses/[analysisId]/brand-workbench";
import { EmptyState } from "@/app/components/empty-state";
import { getApi, type AnalysisRecord } from "@/lib/api";
import { summarizeAnalysis } from "@/lib/primary-app";

export const dynamic = "force-dynamic";

interface BrandSearchParams {
  brand?: string;
  retailer?: string;
}

export default async function BrandWorkbenchDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ analysisId: string }>;
  searchParams: Promise<BrandSearchParams>;
}) {
  const [{ analysisId }, query] = await Promise.all([params, searchParams]);
  const response = await getApi<AnalysisRecord>(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}`,
  );
  if (response.status === 404) notFound();
  if (!response.data) {
    return (
      <main>
        <EmptyState
          eyebrow="Brand Workbench unavailable"
          title="The governed analysis could not be loaded"
          message={response.error ?? "Try again when the API is available."}
        />
      </main>
    );
  }
  const summary = summarizeAnalysis(response.data);
  return (
    <main className="governance-detail-page">
      <header className="page-header compact">
        <div>
          <p className="eyebrow">Workspace · Brand Workbench</p>
          <h1>{summary.category}</h1>
        </div>
        <div className="page-header-actions governance-detail-actions">
          <p>
            Govern private-label, regional, national, and unresolved brand roles
            using persisted Search and PDP evidence.
          </p>
          <Link
            className="button secondary"
            href={`/analyses/${encodeURIComponent(analysisId)}?tab=assortment`}
          >
            Open competitive assortment report
          </Link>
        </div>
      </header>
      <BrandWorkbenchPanel
        analysisId={analysisId}
        scopedRetailerId={query.retailer ?? null}
        focusedBrand={query.brand ?? null}
        routeBasePath={`/workspace/brands/${encodeURIComponent(analysisId)}`}
      />
    </main>
  );
}
