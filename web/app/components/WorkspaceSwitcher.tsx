"use client";

import { useRouter } from "next/navigation";
import type { WorkspaceSummary } from "@/lib/types";

export function WorkspaceSwitcher({
  workspaces,
  current,
  canCreate,
}: {
  workspaces: WorkspaceSummary[];
  current: string;
  canCreate: boolean;
}) {
  const router = useRouter();
  return (
    <select
      className="input"
      value={current}
      aria-label="Workspace"
      onChange={(e) => {
        const v = e.target.value;
        if (v === "__new__") window.location.href = "/org/workspaces";
        else router.push(`/w/${v}/calendar`);
      }}
    >
      {workspaces.map((w) => (
        <option key={w.id} value={w.id}>
          {w.name}
        </option>
      ))}
      {canCreate && <option value="__new__">+ New workspace…</option>}
    </select>
  );
}
