import Link from "next/link";

import { ThemeToggle } from "./theme-toggle";

const navigation = [
  ["Dashboard", "/"],
  ["Collections", "/collections"],
  ["Analyses", "/analyses"],
  ["Automation", "/automation"],
  ["Data Quality", "/data-quality"],
] as const;

export function AppShell({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="app-frame">
      <header className="topbar">
        <Link
          className="brand"
          href="/"
          aria-label="Retail Competitive Intelligence home"
        >
          <span className="brand-mark" aria-hidden="true">
            C
          </span>
          <span className="brand-copy">
            <strong>
              CPG<span>Hero</span>
            </strong>
            <small>Retail Competitive Intelligence</small>
          </span>
        </Link>
        <nav aria-label="Primary navigation">
          {navigation.map(([label, href]) => (
            <Link href={href} key={href}>
              {label}
            </Link>
          ))}
        </nav>
        <div className="shell-actions">
          <div className="environment-pill">
            <span /> Standalone
          </div>
          <ThemeToggle />
        </div>
      </header>
      <div className="page-shell">{children}</div>
    </div>
  );
}
