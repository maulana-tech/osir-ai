import "server-only";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import type { AgentRun, Decision, Me, Policy, Post, Sidebar } from "./types";

const BASE = (process.env.STUDIO_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class StudioError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Where the browser is: the origin Django must see on mutating requests (CSRF). */
async function browserOrigin(): Promise<string> {
  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host") ?? "localhost:3000";
  const proto = h.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  return `${proto}://${host}`;
}

/**
 * Call Studio as the signed-in person. The browser's Django session cookie
 * is forwarded; unsafe methods also carry the CSRF token and an Origin
 * header so Django's CSRF check sees exactly what a same-origin form would send.
 */
export async function studio<T>(path: string, init: RequestInit & { workspaceId?: string } = {}): Promise<T> {
  const jar = await cookies();
  const cookieHeader = jar
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");
  const method = (init.method ?? "GET").toUpperCase();
  const extra: Record<string, string> = {
    Cookie: cookieHeader,
    Accept: "application/json",
  };
  if (init.workspaceId) extra["X-Workspace-Id"] = init.workspaceId;
  if (method !== "GET" && method !== "HEAD") {
    const csrf = jar.get("csrftoken")?.value ?? "";
    const origin = await browserOrigin();
    Object.assign(extra, { "X-CSRFToken": csrf, Origin: origin, Referer: `${origin}/`, "Content-Type": "application/json" });
  }
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    cache: "no-store",
    redirect: "manual",
    headers: { ...extra, ...(init.headers ?? {}) },
  });
  if (res.status === 401 || res.status === 302) {
    redirect(`/accounts/login/?next=${encodeURIComponent("/")}`);
  }
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

// ---------------------------------------------------------------------------
// Typed calls
// ---------------------------------------------------------------------------

export const api = {
  me: (workspaceId?: string) => studio<Me>("/api/web/me/", { workspaceId }),
  selectWorkspace: (workspaceId: string) =>
    studio("/api/web/me/workspace", { method: "POST", body: JSON.stringify({ workspace_id: workspaceId }) }),
  sidebar: (workspaceId: string) => studio<Sidebar>(`/api/web/workspaces/${workspaceId}/sidebar`),

  posts: (workspaceId: string, status?: string, limit = 50) =>
    studio<{ posts: Post[] }>(`/api/v1/posts/?limit=${limit}${status ? `&status=${status}` : ""}`, { workspaceId }).then(
      (r) => r.posts,
    ),

  policy: (workspaceId: string) => studio<Policy>("/api/v1/agent/policy", { workspaceId }),
  setAutonomy: (workspaceId: string, agent_autonomy: string) =>
    studio<Policy>("/api/v1/agent/policy", { method: "PATCH", body: JSON.stringify({ agent_autonomy }), workspaceId }),
  runs: (workspaceId: string, limit = 30) =>
    studio<{ runs: AgentRun[] }>(`/api/v1/agent/runs?limit=${limit}`, { workspaceId }).then((r) => r.runs),
  run: (workspaceId: string, id: string) => studio<AgentRun>(`/api/v1/agent/runs/${id}`, { workspaceId }),
  command: (workspaceId: string, instruction: string, dry_run = false) =>
    studio<AgentRun>("/api/v1/agent/command", {
      method: "POST",
      body: JSON.stringify({ instruction, dry_run }),
      workspaceId,
    }),
  decisions: (workspaceId: string, unreadOnly = true) =>
    studio<{ decisions: Decision[] }>(`/api/v1/agent/decisions?unread_only=${unreadOnly}`, { workspaceId }).then(
      (r) => r.decisions,
    ),
  markRead: (workspaceId: string, id: string) =>
    studio<Decision>(`/api/v1/agent/decisions/${id}/read`, { method: "POST", workspaceId }),
  approvals: (workspaceId: string) => studio<Post[]>("/api/v1/agent/approvals", { workspaceId }),
  approve: (workspaceId: string, id: string, comment = "") =>
    studio<Post>(`/api/v1/agent/approvals/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ comment }),
      workspaceId,
    }),
  reject: (workspaceId: string, id: string, comment: string) =>
    studio<Post>(`/api/v1/agent/approvals/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ comment }),
      workspaceId,
    }),
};
