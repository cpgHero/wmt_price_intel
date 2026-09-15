"use client";

import { useEffect, useState, type FormEvent } from "react";

function safeReturnTo(): string {
  if (typeof window === "undefined") return "/admin/matching-v2";
  const requested =
    new URLSearchParams(window.location.search).get("return_to") ??
    "/admin/matching-v2";
  if (!requested.startsWith("/") || requested.startsWith("//")) {
    return "/admin/matching-v2";
  }
  const target = new URL(requested, window.location.origin);
  if (target.origin !== window.location.origin) return "/admin/matching-v2";
  if (target.pathname.startsWith("/api/")) return "/admin/matching-v2";
  if (target.pathname === "/admin/login") return "/admin/matching-v2";
  return `${target.pathname}${target.search}${target.hash}`;
}

export function AdminLoginWorkspace() {
  const [checking, setChecking] = useState(true);
  const [configured, setConfigured] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [redirecting, setRedirecting] = useState(false);
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
          setRedirecting(true);
          window.location.replace(safeReturnTo());
          return;
        }
        setChecking(false);
      } catch {
        if (!cancelled) {
          setError("Administrator authentication is temporarily unavailable.");
          setChecking(false);
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
      setRedirecting(true);
      window.location.replace(safeReturnTo());
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
          <h2>
            {checking || redirecting
              ? "Checking CPGHero administration access"
              : "Sign in to CPGHero administration"}
          </h2>
          <p>
            {checking
              ? "Verifying the current CPGHero administrator session before opening the requested page."
              : redirecting
                ? "Access verified. Opening the requested Administration page."
                : "Administration is available to CPGHero system administrators through the legacy administrator password session."}
          </p>
        </div>
        {error ? <p className="empty-inline">{error}</p> : null}
        {checking || redirecting ? null : configured ? (
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
