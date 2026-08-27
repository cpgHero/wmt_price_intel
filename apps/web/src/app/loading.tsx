export default function ApplicationLoading() {
  return (
    <main className="application-loading" aria-busy="true" role="status">
      <div className="application-loading-heading">
        <span aria-hidden="true" />
        <div>
          <p className="eyebrow">Retail intelligence</p>
          <h1>Loading the requested workspace…</h1>
          <p>Preparing governed evidence and report controls.</p>
        </div>
      </div>
      <div className="application-loading-grid" aria-hidden="true">
        {Array.from({ length: 6 }, (_, index) => (
          <i key={index} />
        ))}
      </div>
    </main>
  );
}
