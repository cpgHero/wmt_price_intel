"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  applicationNavigation,
  navigationItemIsActive,
} from "@/lib/app-navigation";

import { NavigationIcon } from "./navigation-icon";
import styles from "./primary-navigation.module.css";

export function PrimaryNavigation({
  onNavigate,
}: Readonly<{ onNavigate?: () => void }>) {
  const pathname = usePathname();

  return (
    <nav className={styles.navigation} aria-label="Application navigation">
      {applicationNavigation.map((group) => (
        <section className={styles.group} key={group.id}>
          <h2>{group.label}</h2>
          <div className={styles.links}>
            {group.items.map((item) => {
              const active = navigationItemIsActive(pathname, item);
              return (
                <Link
                  className={active ? styles.active : undefined}
                  href={item.href}
                  key={item.href}
                  aria-current={active ? "page" : undefined}
                  onClick={onNavigate}
                  title={`${item.label} — ${item.description}`}
                >
                  <span className={styles.icon}>
                    <NavigationIcon name={item.icon} />
                  </span>
                  <span className={styles.copy}>
                    <strong>{item.label}</strong>
                    <small>{item.description}</small>
                  </span>
                </Link>
              );
            })}
          </div>
        </section>
      ))}
    </nav>
  );
}
