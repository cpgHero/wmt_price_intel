"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

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
  const [session, setSession] = useState<CustomerSessionState>({
    status: "loading",
  });
  const loginUrl = useMemo(
    () => `/api/auth/login?return_to=${encodeURIComponent(pathname || "/")}`,
    [pathname],
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
  }, []);

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
    <div className={styles.customerSession}>
      <Link
        className={styles.customerIdentity}
        href="/customer"
        title={`Open customer workspace for ${principal.email}`}
      >
        <span className={styles.customerAvatar} aria-hidden="true">
          {initialsForEmail(principal.email)}
        </span>
        <span>
          <strong>{principal.email}</strong>
          <small>{primaryRole(principal.roles)}</small>
        </span>
      </Link>
      <Link className={styles.customerSignOut} href={logoutUrl}>
        Sign out
      </Link>
    </div>
  );
}
