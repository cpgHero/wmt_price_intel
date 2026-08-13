import type { NavigationIcon as NavigationIconName } from "@/lib/app-navigation";

const iconPaths: Record<NavigationIconName, React.ReactNode> = {
  dashboard: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </>
  ),
  intelligence: (
    <>
      <path d="M4 19V9" />
      <path d="M10 19V5" />
      <path d="M16 19v-7" />
      <path d="M22 19H2" />
      <path d="m3 7 6-4 6 5 6-4" />
    </>
  ),
  prices: (
    <>
      <path d="M4 6h16v12H4z" />
      <path d="M7 9h3M14 15h3" />
      <path d="M12 8.5v7" />
      <path d="M14.5 10.5c-.3-1-1.1-1.5-2.5-1.5-1.5 0-2.5.7-2.5 1.8 0 2.7 5 1.2 5 3.5 0 1.1-1 1.7-2.5 1.7-1.4 0-2.3-.5-2.6-1.5" />
    </>
  ),
  collections: (
    <>
      <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5Z" />
      <path d="M4 5.5v16" />
      <path d="M8 7h8M8 11h8" />
    </>
  ),
  automation: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7v5l3.5 2" />
      <path d="M5.5 3.5 3 6M18.5 3.5 21 6" />
    </>
  ),
  matches: (
    <>
      <rect x="3" y="5" width="6" height="6" rx="1.5" />
      <rect x="15" y="13" width="6" height="6" rx="1.5" />
      <path d="M9 8h3a3 3 0 0 1 3 3v5" />
      <path d="m12.5 13.5 2.5 2.5 2.5-2.5" />
    </>
  ),
  brands: (
    <>
      <path d="M4 8.5 10 3h8l2 2v8l-6 6a2.2 2.2 0 0 1-3.1 0L4 12.1a2.5 2.5 0 0 1 0-3.6Z" />
      <circle cx="15.5" cy="7.5" r="1.25" />
    </>
  ),
  quality: (
    <>
      <path d="m12 3 8 3v5c0 5-3.2 8.4-8 10-4.8-1.6-8-5-8-10V6Z" />
      <path d="m8.5 12 2.2 2.2 4.8-5" />
    </>
  ),
  studies: (
    <>
      <path d="M4 4h16v16H4z" />
      <path d="M8 8h8M8 12h5M8 16h7" />
    </>
  ),
  "product-packs": (
    <>
      <path d="m12 3 8 4-8 4-8-4Z" />
      <path d="m4 12 8 4 8-4" />
      <path d="m4 17 8 4 8-4" />
    </>
  ),
};

export function NavigationIcon({
  name,
}: Readonly<{ name: NavigationIconName }>) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.7"
    >
      {iconPaths[name]}
    </svg>
  );
}
