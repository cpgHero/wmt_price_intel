import Link from "next/link";

export const dynamic = "force-static";

export default function PublicHomePage() {
  return (
    <main className="public-home">
      <nav className="public-home__nav" aria-label="Public navigation">
        <Link className="public-home__brand" href="/">
          <span aria-hidden="true">C</span>
          <strong>
            CPG<span>Hero</span>
          </strong>
        </Link>
        <div>
          <Link
            className="button secondary"
            href="/api/auth/login?return_to=/customer"
          >
            Sign in
          </Link>
          <Link className="button primary" href="/customer">
            Open workspace
          </Link>
        </div>
      </nav>

      <section className="public-home__hero">
        <p className="eyebrow">Retail data intelligence platform</p>
        <h1>Source-backed CPG intelligence for retail teams.</h1>
        <p>
          CPGHero helps teams collect store-level retailer data, govern product
          matching, monitor competitive pricing, and turn large retail datasets
          into trusted analytics and shareable reporting.
        </p>
        <div className="button-row">
          <Link
            className="button primary"
            href="/api/auth/login?return_to=/customer"
          >
            Sign in to CPGHero
          </Link>
          <Link
            className="button secondary"
            href="/api/auth/login?return_to=/proximity"
          >
            View proximity analytics
          </Link>
        </div>
      </section>

      <section
        className="public-home__grid"
        aria-label="CPGHero platform pillars"
      >
        <article>
          <span>01</span>
          <h2>Live APIs</h2>
          <p>
            Controlled customer access to CPGHero-masked retailer data APIs with
            usage monitoring, billing governance, and server-side provider
            credential protection.
          </p>
        </article>
        <article>
          <span>02</span>
          <h2>Bulk projects</h2>
          <p>
            Scheduled collection projects for keywords, products, retailers,
            locations, and delivery destinations across email, API retrieval,
            SFTP, and cloud storage workflows.
          </p>
        </article>
        <article>
          <span>03</span>
          <h2>App analytics</h2>
          <p>
            High-performance workspaces for competitive price intelligence,
            proximity, share of search, and review intelligence using governed
            evidence and audit-ready calculations.
          </p>
        </article>
      </section>

      <section className="public-home__trust">
        <div>
          <p className="eyebrow">Built for trust</p>
          <h2>Designed around source authority, tenant security, and speed.</h2>
        </div>
        <ul>
          <li>Server-side collection and provider credential isolation.</li>
          <li>Role, account, workspace, and entitlement boundaries.</li>
          <li>Source-backed metrics with downloadable evidence paths.</li>
          <li>Fast app experiences over very large retail datasets.</li>
        </ul>
      </section>
    </main>
  );
}
