import { SystemOperationsAdmin } from "./system-operations-admin";

export const dynamic = "force-dynamic";

export default function SystemOperationsPage() {
  return (
    <main>
      <header className="page-header compact product-pack-page-header">
        <div>
          <p className="eyebrow">Production readiness</p>
          <h1>System Operations</h1>
        </div>
        <div className="page-header-actions">
          <p>
            Verify the active release, durable work queues, provider controls,
            recent spend, publication state, and recovery evidence.
          </p>
        </div>
      </header>
      <SystemOperationsAdmin />
    </main>
  );
}
