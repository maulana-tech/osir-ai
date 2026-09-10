"use client";

import { useState } from "react";
import { Empty, Section } from "@/app/components/ui";
import { useAction } from "@/app/components/useAction";
import { call } from "@/lib/client";
import type { Category } from "@/lib/types.composer";

export function CategoriesView({ workspaceId, categories }: { workspaceId: string; categories: Category[] }) {
  const { run, busy, Feedback } = useAction();
  const [name, setName] = useState("");
  const [color, setColor] = useState("#0a0a0a");
  const [editing, setEditing] = useState<Category | null>(null);
  const base = `/api/web/workspaces/${workspaceId}/composer/categories`;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Section title="Categories" hint={`${categories.length}`}>
        <p className="mb-3 text-xs" style={{ color: "var(--muted)" }}>
          Categories label posts and drive posting queues (one queue per category and channel).
        </p>
        {categories.length === 0 ? (
          <Empty>No categories yet.</Empty>
        ) : (
          <ul className="divide-y" style={{ borderColor: "var(--line)" }}>
            {categories.map((c) => (
              <li key={c.id} className="flex items-center gap-3 py-2 text-sm">
                {editing?.id === c.id ? (
                  <>
                    <input type="color" value={editing.color} onChange={(e) => setEditing({ ...editing, color: e.target.value })} className="h-8 w-8" />
                    <input className="input" value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
                    <button
                      className="btn btn-accent"
                      disabled={busy}
                      onClick={async () => {
                        const r = await run(() => call(`${base}/${c.id}`, { method: "PATCH", body: JSON.stringify({ name: editing.name, color: editing.color }) }), "Saved");
                        if (r !== undefined) setEditing(null);
                      }}
                    >
                      Save
                    </button>
                    <button className="btn" onClick={() => setEditing(null)}>
                      Cancel
                    </button>
                  </>
                ) : (
                  <>
                    <span className="h-4 w-4 rounded-full" style={{ background: c.color }} />
                    <span className="flex-1 font-semibold">{c.name}</span>
                    <button className="btn" onClick={() => setEditing(c)}>
                      Edit
                    </button>
                    <button className="btn btn-bad" disabled={busy} onClick={() => window.confirm(`Delete "${c.name}"? Posts keep their content; queues tied to it are removed.`) && run(() => call(`${base}/${c.id}`, { method: "DELETE" }), "Deleted")}>
                      Delete
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
        <Feedback />
      </Section>
      <Section title="New category">
        <div className="flex items-center gap-2 text-sm">
          <input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-9 w-9" />
          <input className="input" placeholder="e.g. Educational, Promotional" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} />
          <button
            className="btn btn-accent shrink-0"
            disabled={busy || !name.trim()}
            onClick={async () => {
              const r = await run(() => call(base, { method: "POST", body: JSON.stringify({ name, color }) }), "Created");
              if (r !== undefined) setName("");
            }}
          >
            Add
          </button>
        </div>
      </Section>
    </div>
  );
}
