"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";

import {
  applicationNavigation,
  homeNavigationItem,
  navigationItemIsActive,
  type NavigationGroup,
  type NavigationIcon as NavigationIconName,
} from "@/lib/app-navigation";

import { NavigationIcon } from "./navigation-icon";
import styles from "./primary-navigation.module.css";

const groupIcons: Record<NavigationGroup["id"], NavigationIconName> = {
  workspace: "dashboard",
  intelligence: "intelligence",
  operations: "automation",
  administration: "studies",
};

function subscribeToHydration() {
  return () => undefined;
}

function ChevronIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="m7 10 5 5 5-5" />
    </svg>
  );
}

export function PrimaryNavigation({
  onNavigate,
}: Readonly<{ onNavigate?: () => void }>) {
  const pathname = usePathname();
  const hydrated = useSyncExternalStore(
    subscribeToHydration,
    () => true,
    () => false,
  );
  const activeGroupId =
    applicationNavigation.find((group) =>
      group.items.some((item) => navigationItemIsActive(pathname, item)),
    )?.id ?? "workspace";
  const [openGroups, setOpenGroups] = useState<Set<string>>(
    () => new Set(["workspace", "intelligence", activeGroupId]),
  );
  const [flyout, setFlyout] = useState<{
    group: NavigationGroup;
    top: number;
  } | null>(null);
  const closeTimer = useRef<number | null>(null);

  function navigationIsCompact(element: HTMLElement) {
    return (
      !window.matchMedia("(max-width: 900px)").matches &&
      (element.closest(".shell-compact") !== null ||
        window.matchMedia("(max-width: 1180px)").matches)
    );
  }

  function cancelFlyoutClose() {
    if (closeTimer.current) window.clearTimeout(closeTimer.current);
    closeTimer.current = null;
  }

  function openFlyout(group: NavigationGroup, element: HTMLElement) {
    if (!navigationIsCompact(element)) return false;
    cancelFlyoutClose();
    const bounds = element.getBoundingClientRect();
    const estimatedHeight = 66 + group.items.length * 42;
    setFlyout({
      group,
      top: Math.max(
        8,
        Math.min(bounds.top - 8, window.innerHeight - estimatedHeight - 8),
      ),
    });
    return true;
  }

  function scheduleFlyoutClose() {
    cancelFlyoutClose();
    closeTimer.current = window.setTimeout(() => setFlyout(null), 120);
  }

  function toggleGroup(groupId: string) {
    setOpenGroups((current) => {
      const next = new Set(current);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  }

  return (
    <nav
      className={styles.navigation}
      aria-label="Application navigation"
      data-hydrated={hydrated}
    >
      <Link
        aria-current={pathname === homeNavigationItem.href ? "page" : undefined}
        className={`${styles.homeLink} ${pathname === homeNavigationItem.href ? styles.active : ""}`}
        href={homeNavigationItem.href}
        onClick={onNavigate}
        title={homeNavigationItem.label}
      >
        <span className={styles.icon}>
          <NavigationIcon name={homeNavigationItem.icon} />
        </span>
        <span className={styles.copy}>{homeNavigationItem.label}</span>
      </Link>
      {applicationNavigation.map((group) => {
        const open = openGroups.has(group.id);
        const containsActive = group.id === activeGroupId;
        const childrenId = `navigation-${group.id}`;
        return (
          <section
            className={`${styles.group} ${open ? styles.open : ""} ${containsActive ? styles.containsActive : ""}`}
            key={group.id}
            onMouseLeave={scheduleFlyoutClose}
          >
            <button
              aria-controls={childrenId}
              aria-expanded={open}
              className={styles.groupButton}
              onClick={() => toggleGroup(group.id)}
              onFocus={(event) => openFlyout(group, event.currentTarget)}
              onMouseEnter={(event) => openFlyout(group, event.currentTarget)}
              title={group.label}
              type="button"
            >
              <span className={styles.groupIcon}>
                <NavigationIcon name={groupIcons[group.id]} />
              </span>
              <span className={styles.groupLabel}>{group.label}</span>
              <span className={styles.groupChevron}>
                <ChevronIcon />
              </span>
            </button>
            <div className={styles.children} id={childrenId}>
              <div className={styles.links}>
                {group.items.map((item) => {
                  const active = navigationItemIsActive(pathname, item);
                  return (
                    <Link
                      aria-current={active ? "page" : undefined}
                      className={active ? styles.active : undefined}
                      href={item.href}
                      key={item.href}
                      onClick={onNavigate}
                      title={item.label}
                    >
                      <span className={styles.icon}>
                        <NavigationIcon name={item.icon} />
                      </span>
                      <span className={styles.copy}>{item.label}</span>
                    </Link>
                  );
                })}
              </div>
            </div>
          </section>
        );
      })}
      {flyout
        ? createPortal(
            <aside
              aria-label={`${flyout.group.label} navigation`}
              className={styles.compactFlyout}
              onMouseEnter={cancelFlyoutClose}
              onMouseLeave={scheduleFlyoutClose}
              style={{ top: flyout.top }}
            >
              <header>
                <span className={styles.groupIcon}>
                  <NavigationIcon name={groupIcons[flyout.group.id]} />
                </span>
                <strong>{flyout.group.label}</strong>
              </header>
              <div>
                {flyout.group.items.map((item) => {
                  const active = navigationItemIsActive(pathname, item);
                  return (
                    <Link
                      aria-current={active ? "page" : undefined}
                      className={active ? styles.active : undefined}
                      href={item.href}
                      key={item.href}
                      onClick={() => {
                        setFlyout(null);
                        onNavigate?.();
                      }}
                    >
                      <span className={styles.icon}>
                        <NavigationIcon name={item.icon} />
                      </span>
                      <span>
                        <strong>{item.label}</strong>
                        <small>{item.description}</small>
                      </span>
                    </Link>
                  );
                })}
              </div>
            </aside>,
            document.body,
          )
        : null}
    </nav>
  );
}
