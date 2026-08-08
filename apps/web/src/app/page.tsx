import Link from "next/link";

export default function HomePage() {
  return (
    <main className="dashboard-page">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">Decision-grade market visibility</p>
          <h1>Know the shelf before the market moves.</h1>
          <p className="hero-copy">
            A standalone control plane for retailer collection, auditable
            product matching, price position, and leadership-ready delivery.
          </p>
          <div className="button-row">
            <Link className="button primary" href="/analyses">
              Open analyses
            </Link>
            <Link className="button secondary" href="/collections">
              View collections
            </Link>
          </div>
        </div>
        <aside className="signal-card">
          <span className="live-indicator">
            <i /> System capability
          </span>
          <strong>Three retailer adapters</strong>
          <p>
            Walmart, ALDI, and Amazon Same Day share one durable collection and
            analysis engine.
          </p>
          <div className="signal-grid">
            <span>
              <b>SKIP LOCKED</b>Queue leases
            </span>
            <span>
              <b>Immutable</b>Results
            </span>
            <span>
              <b>Replica-safe</b>Rate limits
            </span>
            <span>
              <b>Auditable</b>Artifacts
            </span>
          </div>
        </aside>
      </section>
      <section className="section-heading">
        <div>
          <span className="section-kicker">Operational workflow</span>
          <h2>From collection to decision</h2>
        </div>
        <p>
          Every view reads authoritative persisted contracts, with no
          reporting-layer metric recalculation.
        </p>
      </section>
      <section className="feature-grid">
        <Link href="/collections" className="feature-card">
          <span>01</span>
          <h3>Collect</h3>
          <p>
            Track retailer tasks, credits, retries, and provider cooldowns as
            they happen.
          </p>
          <b>Collection control →</b>
        </Link>
        <Link href="/analyses" className="feature-card accent">
          <span>02</span>
          <h3>Analyze</h3>
          <p>
            Explore coverage, segments, product matches, QA evidence, and
            methodology.
          </p>
          <b>Analysis workspace →</b>
        </Link>
        <Link href="/data-quality" className="feature-card">
          <span>03</span>
          <h3>Deliver</h3>
          <p>
            Generate leadership HTML, an Excel audit workbook, email draft, and
            audit package.
          </p>
          <b>Quality & delivery →</b>
        </Link>
      </section>
    </main>
  );
}
