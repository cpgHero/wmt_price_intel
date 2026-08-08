export function EmptyState({
  eyebrow,
  title,
  message,
}: Readonly<{ eyebrow: string; title: string; message: string }>) {
  return (
    <section className="empty-state">
      <span className="section-kicker">{eyebrow}</span>
      <h2>{title}</h2>
      <p>{message}</p>
    </section>
  );
}
