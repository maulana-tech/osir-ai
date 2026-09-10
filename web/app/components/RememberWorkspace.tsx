"use client";

import { useEffect } from "react";
import { call } from "@/lib/client";

/** Persist the workspace in the URL as the user's "current" one, like the Django dashboard does. */
export function RememberWorkspace({ workspaceId, current }: { workspaceId: string; current: string | null }) {
  useEffect(() => {
    if (current === workspaceId) return;
    call("/api/web/me/workspace", { method: "POST", body: JSON.stringify({ workspace_id: workspaceId }) }).catch(
      () => undefined,
    );
  }, [workspaceId, current]);
  return null;
}
