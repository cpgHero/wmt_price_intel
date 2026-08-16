import { MatchingV2ReviewAdmin } from "./review-admin";

export const dynamic = "force-dynamic";

export default function MatchingV2ReviewPage() {
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
      <MatchingV2ReviewAdmin />
    </main>
  );
}
