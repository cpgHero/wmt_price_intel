"use client";

import { useEffect, useState, type FormEvent } from "react";

function safeReturnTo(): string {
  if (typeof window === "undefined") return "/admin/customer-auth";
  const requested =
    new URLSearchParams(window.location.search).get("return_to") ??
    "/admin/customer-auth";
  if (
    !requested.startsWith("/") ||
    requested.startsWith("//") ||
    requested.startsWith("/api/") ||
    requested === "/admin/login"
  ) {
    return "/admin/customer-auth";
  }
  return requested;
}

export function AdminLoginWorkspace() {
  const [configured, setConfigured] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function checkSession() {
      try {
        const response = await fetch("/api/admin/session", {
          cache: "no-store",
          credentials: "include",
          headers: { accept: "application/json" },
        });
        const payload = (await response.json()) as {
          authenticated?: boolean;
          configured?: boolean;
        };
        if (cancelled) return;
        setConfigured(payload.configured !== false);
        if (payload.authenticated) {
          window.location.assign(safeReturnTo());
        }
      } catch {
        if (!cancelled) {
          setError("Administrator authentication is temporarily unavailable.");
        }
      }
    }
    void checkSession();
    return () => {
      cancelled = true;
    };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/admin/session", {
        body: JSON.stringify({ password }),
        cache: "no-store",
        credentials: "include",
        headers: {
          accept: "application/json",
          "content-type": "application/json",
        },
        method: "POST",
      });
      if (!response.ok) {
        setError("Administrator credentials were not accepted.");
        return;
      }
      window.location.assign(safeReturnTo());
    } catch {
      setError("Administrator authentication is temporarily unavailable.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main>
      <section className="admin-auth-card">
        <div>
          <p className="eyebrow">Administrator session required</p>
          <h2>Sign in to CPGHero administration</h2>
          <p>
            Admin workspaces are blocked at the route boundary. Sign in to
            continue to the requested protected page.
          </p>
        </div>
        {error ? <p className="empty-inline">{error}</p> : null}
        {configured ? (
          <form onSubmit={submit}>
            <input
              aria-label="Administrator password"
              autoComplete="current-password"
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Administrator password"
              type="password"
              value={password}
            />
            <button disabled={submitting} type="submit">
              {submitting ? "Unlocking…" : "Unlock"}
            </button>
          </form>
        ) : (
          <p>
            Configure the administrator password and session secret before using
            administration.
          </p>
        )}
      </section>
    </main>
  );
}
