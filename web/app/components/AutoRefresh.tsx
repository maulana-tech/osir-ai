"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Re-fetches server components on an interval, so runs and decisions appear without a manual reload. */
export function AutoRefresh({ seconds }: { seconds: number }) {
  const router = useRouter();
  useEffect(() => {
    const id = setInterval(() => router.refresh(), seconds * 1000);
    return () => clearInterval(id);
  }, [router, seconds]);
  return null;
}
