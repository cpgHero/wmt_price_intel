"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import styles from "./app-shell.module.css";

interface CustomerPrincipalResponse {
  principal: {
    account_id: string | null;
    email: string;
    roles: string[];
    workspace_id: string | null;
  };
}

type CustomerSessionState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { principal: CustomerPrincipalResponse["principal"]; status: "signed-in" };

function initialsForEmail(email: string): string {
  const [name] = email.split("@", 1);
  const parts = name.split(/[._+-]+/).filter(Boolean);
  const letters = parts.length > 1 ? [parts[0], parts[1]] : [name.slice(0, 2)];
  return letters.map((part) => part.charAt(0).toUpperCase()).join("");
}

function primaryRole(roles: string[]): string {
  if (roles.includes("account_owner")) return "Account owner";
  if (roles.includes("account_admin")) return "Account admin";
  if (roles.includes("analyst")) return "Analyst";
  if (roles.includes("viewer")) return "Viewer";
  return roles.at(0)?.replaceAll("_", " ") ?? "Customer";
}

export function CustomerAccountMenu() {
  const pathname = usePathname();
  const isAdminWorkspace = pathname?.startsWith("/admin") ?? false;
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [session, setSession] = useState<CustomerSessionState>({
    status: "loading",
  });
  const currentDestination =
    pathname && pathname !== "/" ? pathname : "/customer";
  const loginUrl = useMemo(
    () => `/api/auth/login?return_to=${encodeURIComponent(currentDestination)}`,
    [currentDestination],
  );
  const logoutUrl = useMemo(
    () => `/api/auth/logout?return_to=${encodeURIComponent("/")}`,
    [],
  );

  useEffect(() => {
    let cancelled = false;
    async function loadSession() {
      try {
        const response = await fetch("/api/auth/me", {
          cache: "no-store",
          credentials: "include",
          headers: { accept: "application/json" },
        });
        if (cancelled) return;
        if (response.status === 401 || response.status === 403) {
          setSession({ status: "anonymous" });
          return;
        }
        if (!response.ok) {
          setSession({ status: "anonymous" });
          return;
        }
        const payload = (await response.json()) as CustomerPrincipalResponse;
        setSession({ status: "signed-in", principal: payload.principal });
      } catch {
        if (!cancelled) setSession({ status: "anonymous" });
      }
    }
    loadSession();
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    function onPointerDown(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [menuOpen]);

  if (session.status === "loading") {
    return (
      <span className={styles.customerSessionSkeleton} aria-hidden="true" />
    );
  }

  if (session.status === "anonymous") {
    if (isAdminWorkspace) {
      return (
        <span
          className={styles.customerSignIn}
          title="This administrator workspace uses the protected admin session below."
        >
          Admin protected
        </span>
      );
    }

    return (
      <Link className={styles.customerSignIn} href={loginUrl}>
        Sign in
      </Link>
    );
  }

  const { principal } = session;
  return (
    <div className={styles.customerSession} ref={menuRef}>
      <button
        className={styles.customerIdentity}
        type="button"
        aria-expanded={menuOpen}
        aria-haspopup="menu"
        title={`Open account menu for ${principal.email}`}
        onClick={() => setMenuOpen((open) => !open)}
      >
        <span className={styles.customerAvatar} aria-hidden="true">
          {initialsForEmail(principal.email)}
        </span>
        <span>
          <strong>{principal.email}</strong>
          <small>{primaryRole(principal.roles)}</small>
        </span>
      </button>
      {menuOpen ? (
        <div className={styles.customerMenu} role="menu">
          <Link
            className={styles.customerMenuItem}
            href="/customer"
            role="menuitem"
            onClick={() => setMenuOpen(false)}
          >
            My workspace
          </Link>
          <Link
            className={styles.customerMenuItem}
            href={logoutUrl}
            role="menuitem"
            onClick={() => setMenuOpen(false)}
          >
            Sign out
          </Link>
        </div>
      ) : null}
    </div>
  );
}
