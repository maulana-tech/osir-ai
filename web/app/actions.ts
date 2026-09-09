"use server";

import { revalidatePath } from "next/cache";
import { studio } from "@/lib/studio";

function refresh() {
  revalidatePath("/");
  revalidatePath("/approvals");
  revalidatePath("/runs");
}

export async function sendCommand(formData: FormData) {
  const instruction = String(formData.get("instruction") ?? "").trim();
  const dryRun = formData.get("dry_run") === "on";
  if (!instruction) return;
  await studio.command(instruction, dryRun);
  refresh();
}

export async function setAutonomy(formData: FormData) {
  const level = String(formData.get("agent_autonomy") ?? "");
  if (!level) return;
  await studio.setAutonomy(level);
  refresh();
}

export async function markHandled(formData: FormData) {
  await studio.markRead(String(formData.get("id")));
  refresh();
}

export async function approvePost(formData: FormData) {
  await studio.approve(String(formData.get("id")), String(formData.get("comment") ?? ""));
  refresh();
}

export async function rejectPost(formData: FormData) {
  const comment = String(formData.get("comment") ?? "").trim() || "Rejected from the console";
  await studio.reject(String(formData.get("id")), comment);
  refresh();
}
