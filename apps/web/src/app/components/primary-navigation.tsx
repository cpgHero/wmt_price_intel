"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import {
  applicationNavigation,
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
  const activeGroupId =
    applicationNavigation.find((group) =>
      group.items.some((item) => navigationItemIsActive(pathname, item)),
    )?.id ?? "workspace";
  const [openGroups, setOpenGroups] = useState<Set<string>>(
    () => new Set(["workspace", "intelligence", activeGroupId]),
  );

  function toggleGroup(groupId: string) {
    setOpenGroups((current) => {
      const next = new Set(current);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  }

  return (
    <nav className={styles.navigation} aria-label="Application navigation">
      {applicationNavigation.map((group) => {
        const open = openGroups.has(group.id);
        const containsActive = group.id === activeGroupId;
        const childrenId = `navigation-${group.id}`;
        return (
          <section
            className={`${styles.group} ${open ? styles.open : ""} ${containsActive ? styles.containsActive : ""}`}
            key={group.id}
          >
            <button
              aria-controls={childrenId}
              aria-expanded={open}
              className={styles.groupButton}
              onClick={() => toggleGroup(group.id)}
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
    </nav>
  );
}
