"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function RunActions({
  runId,
  cancellable,
}: Readonly<{ runId: string; cancellable: boolean }>) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function cancel() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(
        `/api/collection-runs/${encodeURIComponent(runId)}/cancel`,
        { method: "POST" },
      );
      if (!response.ok) throw new Error("The run could not be cancelled.");
      router.refresh();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The run could not be cancelled.",
      );
    } finally {
      setBusy(false);
    }
  }
  if (!cancellable) return null;
  return (
    <div className="run-actions">
      <button
        className="button danger"
        type="button"
        disabled={busy}
        onClick={() => void cancel()}
      >
        {busy ? "Cancelling…" : "Cancel run"}
      </button>
      {error && <small role="alert">{error}</small>}
    </div>
  );
}
