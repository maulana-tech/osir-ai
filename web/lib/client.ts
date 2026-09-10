"use client";

/**
 * Browser-side calls to Studio through the same-origin proxy. Django's CSRF
 * cookie is readable (not HttpOnly) and echoed in the X-CSRFToken header.
 */

function cookie(name: string): string {
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : "";
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function call<T>(path: string, init: RequestInit & { workspaceId?: string } = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.workspaceId) headers["X-Workspace-Id"] = init.workspaceId;
  if (method !== "GET" && method !== "HEAD") {
    headers["X-CSRFToken"] = cookie("csrftoken");
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, { ...init, credentials: "same-origin", headers: { ...headers, ...(init.headers ?? {}) } });
  if (res.status === 401) {
    window.location.href = `/accounts/login/?next=${encodeURIComponent(window.location.pathname)}`;
    throw new ApiError(401, "Signed out");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? body.message ?? JSON.stringify(body);
    } catch {
      /* non-JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}
