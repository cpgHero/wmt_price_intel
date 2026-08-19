import { MatchingV2ReviewAdmin } from "./review-admin";

export const dynamic = "force-dynamic";

interface MatchingSearchParams {
  pack?: string;
  competitor?: string;
  benchmark_product?: string;
  competitor_product?: string;
}

export default async function MatchingV2ReviewPage({
  searchParams,
}: Readonly<{ searchParams: Promise<MatchingSearchParams> }>) {
  const parameters = await searchParams;
  return (
    <main>
      <header className="page-header compact product-pack-page-header">
        <div>
          <p className="eyebrow">Evidence-governed administration</p>
          <h1>Match Certification</h1>
        </div>
        <div className="page-header-actions">
          <p>
            Approve or reject deterministic product relationships once, retain
            an immutable audit trail, and reopen only decisions that are
            explicitly flagged.
          </p>
        </div>
      </header>
      <MatchingV2ReviewAdmin
        initialContext={{
          productPackId: parameters.pack ?? null,
          competitorRetailerId: parameters.competitor ?? null,
          benchmarkProductId: parameters.benchmark_product ?? null,
          competitorProductId: parameters.competitor_product ?? null,
        }}
      />
    </main>
  );
}
