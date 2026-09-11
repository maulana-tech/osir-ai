"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { call } from "@/lib/client";
import type { LibraryScope, MediaFolder } from "@/lib/types.media";

function NameForm({ initial = "", onSubmit, onCancel }: { initial?: string; onSubmit: (name: string) => Promise<void>; onCancel: () => void }) {
  const [name, setName] = useState(initial);
  const [err, setErr] = useState("");
  return (
    <form
      className="flex items-center gap-1 px-2 py-1"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(name)
          .then(onCancel)
          .catch((x) => setErr(x.message));
      }}
    >
      <input className="input py-0.5 text-xs" autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Folder name" onKeyDown={(e) => e.key === "Escape" && onCancel()} />
      <button className="btn py-0.5 text-xs" type="submit" disabled={!name.trim()}>
        OK
      </button>
      {err && <span className="text-[10px]" style={{ color: "var(--bad)" }}>{err}</span>}
    </form>
  );
}

function Node({ f, depth, current, scope, onSelect }: { f: MediaFolder; depth: number; current: string; scope: LibraryScope; onSelect: (id: string) => void }) {
  const router = useRouter();
  const [mode, setMode] = useState<"rename" | "new" | null>(null);
  const active = current === f.id;
  const base = `${scope.apiBase}/folders`;
  return (
    <li>
      <div className={`group flex items-center gap-1 rounded-md px-2 py-1 text-xs ${active ? "" : "hover:bg-neutral-100"}`} style={{ paddingLeft: 8 + depth * 12, background: active ? "#0a0a0a" : undefined, color: active ? "#fff" : undefined }}>
        <button className="min-w-0 flex-1 truncate text-left" onClick={() => onSelect(f.id)}>
          {f.name}
        </button>
        {scope.canManageFolders && (
          <span className="hidden gap-1 group-hover:flex">
            {depth < 2 && (
              <button title="New subfolder" onClick={() => setMode("new")}>
                +
              </button>
            )}
            <button title="Rename" onClick={() => setMode("rename")}>
              ✎
            </button>
            <button
              title="Delete (files move up)"
              onClick={() => {
                if (window.confirm(`Delete folder "${f.name}"? Its files and subfolders move to the parent.`)) {
                  call(`${base}/${f.id}`, { method: "DELETE" })
                    .then(() => {
                      if (active) onSelect("");
                      router.refresh();
                    })
                    .catch(() => {});
                }
              }}
            >
              ×
            </button>
          </span>
        )}
      </div>
      {mode === "rename" && (
        <NameForm
          initial={f.name}
          onCancel={() => setMode(null)}
          onSubmit={async (name) => {
            await call(`${base}/${f.id}`, { method: "PATCH", body: JSON.stringify({ name }) });
            router.refresh();
          }}
        />
      )}
      {mode === "new" && (
        <NameForm
          onCancel={() => setMode(null)}
          onSubmit={async (name) => {
            await call(base, { method: "POST", body: JSON.stringify({ name, parent_folder_id: f.id }) });
            router.refresh();
          }}
        />
      )}
      {f.children.length > 0 && (
        <ul>
          {f.children.map((c) => (
            <Node key={c.id} f={c} depth={depth + 1} current={current} scope={scope} onSelect={onSelect} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function FolderTree({ folders, current, starred, scope, onSelect, onStarred }: { folders: MediaFolder[]; current: string; starred: boolean; scope: LibraryScope; onSelect: (id: string) => void; onStarred: () => void }) {
  const router = useRouter();
  const [creating, setCreating] = useState(false);
  const item = (active: boolean) => ({ background: active ? "#0a0a0a" : undefined, color: active ? "#fff" : undefined });
  return (
    <div className="text-sm">
      <div className="mb-1 flex items-center justify-between px-2 text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
        <span>Folders</span>
        {scope.canManageFolders && (
          <button title="New folder" onClick={() => setCreating(true)}>
            +
          </button>
        )}
      </div>
      <ul className="space-y-0.5">
        <li>
          <button className="w-full rounded-md px-2 py-1 text-left text-xs hover:bg-neutral-100" style={item(!current && !starred)} onClick={() => onSelect("")}>
            All files
          </button>
        </li>
        <li>
          <button className="w-full rounded-md px-2 py-1 text-left text-xs hover:bg-neutral-100" style={item(starred)} onClick={onStarred}>
            ★ Starred
          </button>
        </li>
        {folders.map((f) => (
          <Node key={f.id} f={f} depth={0} current={current} scope={scope} onSelect={onSelect} />
        ))}
      </ul>
      {creating && (
        <NameForm
          onCancel={() => setCreating(false)}
          onSubmit={async (name) => {
            await call(`${scope.apiBase}/folders`, { method: "POST", body: JSON.stringify({ name }) });
            router.refresh();
          }}
        />
      )}
    </div>
  );
}
