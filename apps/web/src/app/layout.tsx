import type { Metadata } from "next";

import { AppShell } from "./components/app-shell";
import "./styles.css";

export const metadata: Metadata = {
  title: "Retail Competitive Intelligence",
  description: "Standalone retail collection and comparison control plane.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
