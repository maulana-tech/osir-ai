"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ApiError } from "@/lib/client";

/** Run a mutation, surface its error, and re-render server components on success. */
export function useAction() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  async function run<T>(fn: () => Promise<T>, done?: string): Promise<T | undefined> {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const out = await fn();
      if (done) setNotice(done);
      router.refresh();
      return out;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Something went wrong");
      return undefined;
    } finally {
      setBusy(false);
    }
  }

  const Feedback = () =>
    error ? (
      <p className="mt-2 text-sm" style={{ color: "var(--bad)" }} role="alert">
        {error}
      </p>
    ) : notice ? (
      <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>
        {notice}
      </p>
    ) : null;

  return { run, busy, error, notice, Feedback };
}
