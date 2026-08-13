export default function PriceIntelligenceLoading() {
  return (
    <main className="price-monitoring-page" aria-busy="true">
      <header className="pm-masthead pi-masthead pi-loading-masthead">
        <div>
          <p className="eyebrow">Price Intelligence</p>
          <h1>Loading governed Search evidence…</h1>
          <p>
            Preparing product, location-master, price, and distribution views.
          </p>
        </div>
      </header>
      <section
        className="pi-loading-grid"
        aria-label="Loading price intelligence"
      >
        {Array.from({ length: 6 }, (_, index) => (
          <i key={index} />
        ))}
      </section>
    </main>
  );
}
