import "server-only";
import type { AgentRun, Decision, Policy, Post } from "./types";

const BASE = (process.env.STUDIO_URL ?? "http://localhost:8000").replace(/\/$/, "");
const KEY = process.env.STUDIO_API_KEY ?? "";

export class StudioError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}/api/v1${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${KEY}`,
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? body.message ?? JSON.stringify(body);
    } catch {
      /* non-JSON error body */
    }
    throw new StudioError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const studio = {
  policy: () => call<Policy>("/agent/policy"),
  setAutonomy: (agent_autonomy: string) =>
    call<Policy>("/agent/policy", { method: "PATCH", body: JSON.stringify({ agent_autonomy }) }),
  runs: (limit = 30) => call<{ runs: AgentRun[] }>(`/agent/runs?limit=${limit}`).then((r) => r.runs),
  run: (id: string) => call<AgentRun>(`/agent/runs/${id}`),
  command: (instruction: string, dry_run = false) =>
    call<AgentRun>("/agent/command", { method: "POST", body: JSON.stringify({ instruction, dry_run }) }),
  decisions: (unreadOnly = true) =>
    call<{ decisions: Decision[] }>(`/agent/decisions?unread_only=${unreadOnly}`).then((r) => r.decisions),
  markRead: (id: string) => call<Decision>(`/agent/decisions/${id}/read`, { method: "POST" }),
  approvals: () => call<Post[]>("/agent/approvals"),
  approve: (id: string, comment = "") =>
    call<Post>(`/agent/approvals/${id}/approve`, { method: "POST", body: JSON.stringify({ comment }) }),
  reject: (id: string, comment: string) =>
    call<Post>(`/agent/approvals/${id}/reject`, { method: "POST", body: JSON.stringify({ comment }) }),
};
