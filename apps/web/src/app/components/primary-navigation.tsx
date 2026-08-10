"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navigation = [
  ["Dashboard", "/"],
  ["Collections", "/collections"],
  ["Reports", "/analyses"],
  ["Schedules & Alerts", "/automation"],
  ["Data Quality", "/data-quality"],
] as const;

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export function PrimaryNavigation() {
  const pathname = usePathname();
  return (
    <nav aria-label="Primary navigation">
      {navigation.map(([label, href]) => (
        <Link
          href={href}
          key={href}
          aria-current={isActive(pathname, href) ? "page" : undefined}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}
