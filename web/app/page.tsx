import { studio } from "@/lib/studio";
import type { Autonomy } from "@/lib/types";
import { markHandled, sendCommand, setAutonomy } from "./actions";
import { Empty, RunRow, Section, timeAgo } from "./components/ui";

export const dynamic = "force-dynamic";

const LEVEL_COPY: Record<Autonomy, string> = {
  off: "Observe and report only.",
  draft_only: "Replies to routine inbox items, drafts go through approval.",
  autopilot: "May also schedule routine posts itself when the workflow and key allow it.",
};

export default async function Overview() {
  const [policy, decisions, runs] = await Promise.all([studio.policy(), studio.decisions(true), studio.runs(8)]);
  const running = runs.filter((r) => r.status === "running" || r.status === "pending").length;

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        <Section title="Ask Osir" hint={policy.agentcore_configured ? "runs on AgentCore" : "runs on the local worker"}>
          <form action={sendCommand} className="space-y-3">
            <textarea
              name="instruction"
              rows={3}
              required
              className="input"
              placeholder='e.g. "Plan next week for the LinkedIn page from the idea board" or "How did last week&apos;s launch post do?"'
            />
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-xs" style={{ color: "var(--muted)" }}>
                <input type="checkbox" name="dry_run" /> dry run (no writes)
              </label>
              <button className="btn btn-accent" type="submit">
                Send to agent
              </button>
            </div>
          </form>
          {running > 0 && (
            <p className="mt-3 text-xs" style={{ color: "var(--accent)" }}>
              {running} run{running > 1 ? "s" : ""} in progress. This page refreshes every 15 seconds.
            </p>
          )}
        </Section>

        <Section title="Needs your decision" hint={`${decisions.length} open`}>
          {decisions.length === 0 ? (
            <Empty>Nothing waiting on you. The agent is handling the routine work.</Empty>
          ) : (
            <ul className="divide-y" style={{ borderColor: "var(--line)" }}>
              {decisions.map((d) => (
                <li key={d.id} className="flex gap-4 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className={d.event_type === "agent_digest" ? "pill" : "pill pill-accent"}>
                        {d.event_type === "agent_digest" ? "digest" : "decision"}
                      </span>
                      <span className="text-sm font-semibold">{d.title}</span>
                      <span className="text-xs" style={{ color: "var(--muted)" }}>
                        {timeAgo(d.created_at)}
                      </span>
                    </div>
                    <p className="mt-1 whitespace-pre-wrap text-sm" style={{ color: "var(--muted)" }}>
                      {d.body}
                    </p>
                  </div>
                  <form action={markHandled} className="shrink-0 self-start">
                    <input type="hidden" name="id" value={d.id} />
                    <button className="btn" type="submit">
                      Handled
                    </button>
                  </form>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <div className="space-y-6">
        <Section title="Autonomy" hint={policy.workspace_name}>
          <form action={setAutonomy} className="space-y-2">
            {policy.autonomy_levels.map((level) => (
              <label
                key={level}
                className="flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm"
                style={{ borderColor: policy.agent_autonomy === level ? "var(--accent)" : "var(--line)" }}
              >
                <input
                  type="radio"
                  name="agent_autonomy"
                  value={level}
                  defaultChecked={policy.agent_autonomy === level}
                  disabled={!policy.can_change_policy}
                  className="mt-1"
                />
                <span>
                  <span className="font-semibold capitalize">{level.replace("_", " ")}</span>
                  <span className="block text-xs" style={{ color: "var(--muted)" }}>
                    {LEVEL_COPY[level]}
                  </span>
                </span>
              </label>
            ))}
            {policy.can_change_policy && (
              <button className="btn w-full justify-center" type="submit">
                Save
              </button>
            )}
          </form>
          <dl className="mt-4 space-y-1 text-xs" style={{ color: "var(--muted)" }}>
            <div className="flex justify-between">
              <dt>Approval workflow</dt>
              <dd>{policy.approval_workflow_mode}</dd>
            </div>
            <div className="flex justify-between">
              <dt>Direct scheduling</dt>
              <dd>{policy.direct_scheduling_allowed ? "allowed" : "blocked by workflow"}</dd>
            </div>
            <div className="flex justify-between">
              <dt>Key may publish</dt>
              <dd>{policy.can_publish ? "yes" : "no"}</dd>
            </div>
          </dl>
        </Section>

        <Section title="Recent runs">
          {runs.length === 0 ? (
            <Empty>No runs yet.</Empty>
          ) : (
            <div className="-mx-3">
              {runs.map((r) => (
                <RunRow key={r.id} run={r} />
              ))}
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}
