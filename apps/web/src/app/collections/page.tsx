export default function CollectionsPage() {
  return (
    <main>
      <header className="page-header compact">
        <div>
          <p className="eyebrow">Collection control</p>
          <h1>Runs & operations</h1>
        </div>
        <p>
          Open a run monitor using its durable run identifier. The monitor reads
          exact task aggregates and shared provider state from Postgres.
        </p>
      </header>
      <section className="content-card split-card">
        <div>
          <span className="section-kicker">Run monitor route</span>
          <h2>/collections/runs/&lt;run-id&gt;</h2>
          <p>
            Shows retailer/status counts, pages, estimated and actual credits,
            rate windows, 429 cooldown, retries, failures, elapsed time, and
            cancellation.
          </p>
        </div>
        <div className="status-stack">
          <span>
            <i className="dot green" /> Durable queue ready
          </span>
          <span>
            <i className="dot green" /> Replica-safe provider budget
          </span>
          <span>
            <i className="dot green" /> Idempotent task identity
          </span>
        </div>
      </section>
    </main>
  );
}
