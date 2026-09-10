"use server";

import { revalidatePath } from "next/cache";
import { api } from "@/lib/studio";

function ws(formData: FormData): string {
  const id = String(formData.get("workspace_id") ?? "");
  if (!id) throw new Error("workspace_id missing");
  return id;
}

function refresh(workspaceId: string) {
  revalidatePath(`/w/${workspaceId}`, "layout");
}

export async function sendCommand(formData: FormData) {
  const workspaceId = ws(formData);
  const instruction = String(formData.get("instruction") ?? "").trim();
  const dryRun = formData.get("dry_run") === "on";
  if (!instruction) return;
  await api.command(workspaceId, instruction, dryRun);
  refresh(workspaceId);
}

export async function setAutonomy(formData: FormData) {
  const workspaceId = ws(formData);
  const level = String(formData.get("agent_autonomy") ?? "");
  if (!level) return;
  await api.setAutonomy(workspaceId, level);
  refresh(workspaceId);
}

export async function markHandled(formData: FormData) {
  const workspaceId = ws(formData);
  await api.markRead(workspaceId, String(formData.get("id")));
  refresh(workspaceId);
}

export async function approvePost(formData: FormData) {
  const workspaceId = ws(formData);
  await api.approve(workspaceId, String(formData.get("id")), String(formData.get("comment") ?? ""));
  refresh(workspaceId);
}

export async function rejectPost(formData: FormData) {
  const workspaceId = ws(formData);
  const comment = String(formData.get("comment") ?? "").trim() || "Rejected from the console";
  await api.reject(workspaceId, String(formData.get("id")), comment);
  refresh(workspaceId);
}
