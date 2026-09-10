import { redirect } from "next/navigation";
import { api } from "@/lib/studio";

export const dynamic = "force-dynamic";

/** Entry point: send the person to the workspace they were last in. */
export default async function Home() {
  const me = await api.me();
  if (!me.user.tos_accepted) redirect("/accounts/accept-terms/");
  const target = me.current_workspace_id ?? me.workspaces[0]?.id;
  if (!target) redirect("/workspaces/");
  redirect(`/w/${target}/calendar`);
}
