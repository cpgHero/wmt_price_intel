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
            Independently review deterministic product relationships, resolve
            disagreements, and create immutable category gold sets.
          </p>
        </div>
      </header>
      <MatchingV2ReviewAdmin />
    </main>
  );
}
