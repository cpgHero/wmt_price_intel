import type { Metadata } from "next";
import Script from "next/script";

import { ApplicationContextProvider } from "./components/application-context";
import { AppShell } from "./components/app-shell";
import "./styles.css";

export const metadata: Metadata = {
  title: {
    default: "Retail Competitive Intelligence | CPGHero",
    template: "%s | CPGHero Retail CI",
  },
  description: "Standalone retail collection and comparison control plane.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Script id="theme-init" strategy="beforeInteractive">
          {`(() => {
            try {
              const saved = localStorage.getItem("rci-theme");
              const theme = saved === "light" || saved === "dark"
                ? saved
                : matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
              document.documentElement.dataset.theme = theme;
              document.documentElement.style.colorScheme = theme;
            } catch (_) {}
          })();`}
        </Script>
        <ApplicationContextProvider>
          <AppShell>{children}</AppShell>
        </ApplicationContextProvider>
      </body>
    </html>
  );
}
