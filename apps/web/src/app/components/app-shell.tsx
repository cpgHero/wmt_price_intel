"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  useEffect,
  useId,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

import { activeNavigationItem } from "@/lib/app-navigation";

import { useApplicationContext } from "./application-context";
import { ContextControlBar } from "./context-control-bar";
import { PrimaryNavigation } from "./primary-navigation";
import { ThemeToggle } from "./theme-toggle";
import styles from "./app-shell.module.css";

const sidebarStorageKey = "rci-sidebar-compact";
const sidebarPreferenceEvent = "rci-sidebar-preference";

function sidebarPreferenceSnapshot(): boolean {
  try {
    return window.localStorage.getItem(sidebarStorageKey) === "true";
  } catch {
    return false;
  }
}

function subscribeToSidebarPreference(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(sidebarPreferenceEvent, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(sidebarPreferenceEvent, onChange);
  };
}

function SidebarBrand({
  compact = false,
  onNavigate,
}: Readonly<{ compact?: boolean; onNavigate?: () => void }>) {
  return (
    <Link
      className={styles.brand}
      href="/"
      aria-label="CPGHero Retail Competitive Intelligence home"
      onClick={onNavigate}
    >
      <span className={styles.brandMark} aria-hidden="true">
        C
      </span>
      <span className={styles.brandCopy} aria-hidden={compact || undefined}>
        <strong>
          CPG<span>Hero</span>
        </strong>
        <small>Retail Competitive Intelligence</small>
      </span>
    </Link>
  );
}

function CollapseIcon({ compact }: Readonly<{ compact: boolean }>) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d={compact ? "m9 6 6 6-6 6" : "m15 6-6 6 6 6"} />
    </svg>
  );
}

function MenuIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="m6 6 12 12M18 6 6 18" />
    </svg>
  );
}

export function AppShell({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();
  const activeItem = activeNavigationItem(pathname);
  const { definition: contextDefinition } = useApplicationContext();
  const compact = useSyncExternalStore(
    subscribeToSidebarPreference,
    sidebarPreferenceSnapshot,
    () => false,
  );
  const [mobileOpen, setMobileOpen] = useState(false);
  const mobileNavigationId = useId();
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const mobileSidebarRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!mobileOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMobileOpen(false);
        menuButtonRef.current?.focus();
        return;
      }
      if (event.key !== "Tab") return;

      const focusable = Array.from(
        mobileSidebarRef.current?.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      );
      const first = focusable.at(0);
      const last = focusable.at(-1);
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [mobileOpen]);

  function toggleCompact() {
    try {
      window.localStorage.setItem(sidebarStorageKey, String(!compact));
      window.dispatchEvent(new Event(sidebarPreferenceEvent));
    } catch {
      // The navigation still works when storage is unavailable.
    }
  }

  function closeMobileNavigation({ restoreFocus = false } = {}) {
    setMobileOpen(false);
    if (restoreFocus) menuButtonRef.current?.focus();
  }

  return (
    <div className={`${styles.frame} ${compact ? "shell-compact" : ""}`}>
      <a className={styles.skipLink} href="#main-content">
        Skip to main content
      </a>
      <aside className={styles.sidebar} aria-label="Application sidebar">
        <div className={styles.sidebarHeader}>
          <SidebarBrand compact={compact} />
          <button
            className={styles.collapseButton}
            type="button"
            aria-label={compact ? "Expand sidebar" : "Collapse sidebar"}
            aria-pressed={compact}
            onClick={toggleCompact}
            title={compact ? "Expand sidebar" : "Collapse sidebar"}
          >
            <CollapseIcon compact={compact} />
          </button>
        </div>
        <PrimaryNavigation />
        <footer className={styles.sidebarFooter}>
          <span className={styles.liveDot} aria-hidden="true" />
          <span>
            <strong>Standalone workspace</strong>
            <small>Railway production</small>
          </span>
        </footer>
      </aside>

      <div className={styles.application}>
        <header className={styles.topbar}>
          <button
            className={styles.mobileMenuButton}
            type="button"
            ref={menuButtonRef}
            aria-controls={mobileNavigationId}
            aria-expanded={mobileOpen}
            aria-label="Open application navigation"
            onClick={() => setMobileOpen(true)}
          >
            <MenuIcon />
          </button>
          {contextDefinition ? (
            <ContextControlBar definition={contextDefinition} />
          ) : (
            <div className={styles.pageContext}>
              <span>
                {activeItem ? activeItem.label : "Retail intelligence"}
              </span>
              <small>{activeItem?.description ?? "Standalone workspace"}</small>
            </div>
          )}
          <div className={styles.topbarActions}>
            <span className={styles.statusPill}>
              <span className={styles.liveDot} aria-hidden="true" />
              Live
            </span>
            <ThemeToggle />
          </div>
        </header>
        <div className={styles.pageShell}>
          <div id="main-content" tabIndex={-1}>
            {children}
          </div>
        </div>
      </div>

      <div
        className={`${styles.mobileLayer} ${mobileOpen ? styles.open : ""}`}
        aria-hidden={!mobileOpen}
      >
        <button
          className={styles.backdrop}
          type="button"
          tabIndex={mobileOpen ? 0 : -1}
          aria-label="Dismiss navigation overlay"
          onClick={() => closeMobileNavigation({ restoreFocus: true })}
        />
        <aside
          className={styles.mobileSidebar}
          id={mobileNavigationId}
          ref={mobileSidebarRef}
          aria-label="Mobile application navigation"
          aria-modal={mobileOpen || undefined}
          role={mobileOpen ? "dialog" : undefined}
        >
          <div className={styles.sidebarHeader}>
            <SidebarBrand onNavigate={() => closeMobileNavigation()} />
            <button
              className={styles.collapseButton}
              type="button"
              ref={closeButtonRef}
              aria-label="Close application navigation"
              onClick={() => closeMobileNavigation({ restoreFocus: true })}
            >
              <CloseIcon />
            </button>
          </div>
          <PrimaryNavigation onNavigate={() => closeMobileNavigation()} />
          <footer className={styles.sidebarFooter}>
            <span className={styles.liveDot} aria-hidden="true" />
            <span>
              <strong>Standalone workspace</strong>
              <small>Railway production</small>
            </span>
          </footer>
        </aside>
      </div>
    </div>
  );
}
