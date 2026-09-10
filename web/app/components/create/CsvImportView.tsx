"use client";

import Link from "next/link";
import { useState } from "react";
import { Section } from "@/app/components/ui";
import { ApiError, call } from "@/lib/client";

type Upload = { headers: string[]; preview_rows: string[][]; total_rows: number; auto_mapping: Record<string, number>; fields: string[] };
type Validation = { total_rows: number; valid_count: number; errors: { row: number; errors: string[] }[]; has_more_errors: boolean };
type Result = { created_count: number; error_count: number; total_rows: number };

const LABEL: Record<string, string> = { date: "Date (YYYY-MM-DD)", time: "Time (HH:MM)", platforms: "Platforms (comma separated)", caption: "Caption", media_url: "Media URL", category: "Category", tags: "Tags", first_comment: "First comment" };

export function CsvImportView({ workspaceId }: { workspaceId: string }) {
  const base = `/api/web/workspaces/${workspaceId}/composer/csv`;
  const [upload, setUpload] = useState<Upload | null>(null);
  const [mapping, setMapping] = useState<Record<string, number | "">>({});
  const [validation, setValidation] = useState<Validation | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function onFile(file: File | null) {
    if (!file) return;
    setBusy(true);
    setErr("");
    setValidation(null);
    try {
      const fd = new FormData();
      fd.append("csv_file", file);
      const csrf = decodeURIComponent(document.cookie.match(/(?:^|; )csrftoken=([^;]*)/)?.[1] ?? "");
      const res = await fetch(`${base}/upload`, { method: "POST", body: fd, headers: { "X-CSRFToken": csrf } });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail ?? "Upload failed");
      setUpload(body);
      setMapping(Object.fromEntries(body.fields.map((f: string) => [f, body.auto_mapping[f] ?? ""])));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  const step = async <T,>(fn: () => Promise<T>, after: (r: T) => void) => {
    setBusy(true);
    setErr("");
    try {
      after(await fn());
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    return (
      <Section title="Done">
        <p className="text-sm">
          Created {result.created_count} of {result.total_rows} posts{result.error_count > 0 && `, ${result.error_count} skipped`}.
        </p>
        <div className="mt-3 flex gap-2">
          <Link href={`/w/${workspaceId}/calendar`} className="btn btn-accent">
            Open the calendar
          </Link>
          <button
            className="btn"
            onClick={() => {
              setResult(null);
              setUpload(null);
              setValidation(null);
            }}
          >
            Import another file
          </button>
        </div>
      </Section>
    );
  }

  return (
    <div className="space-y-6">
      <Section title="1. Upload">
        <p className="mb-2 text-xs" style={{ color: "var(--muted)" }}>
          One row per post. Recognised columns: date, time, platform(s), caption, media URL, category, tags, first comment. Max 5 MB.
        </p>
        <input type="file" accept=".csv,text/csv" disabled={busy} onChange={(e) => onFile(e.target.files?.[0] ?? null)} />
        {err && (
          <p className="mt-2 text-sm" style={{ color: "var(--bad)" }} role="alert">
            {err}
          </p>
        )}
      </Section>

      {upload && (
        <Section title={`2. Map columns (${upload.total_rows} rows)`}>
          <div className="grid gap-2 sm:grid-cols-2">
            {upload.fields.map((f) => (
              <label key={f} className="flex items-center gap-2 text-sm">
                <span className="w-44 text-xs" style={{ color: "var(--muted)" }}>
                  {LABEL[f] ?? f}
                </span>
                <select className="input" value={mapping[f] ?? ""} onChange={(e) => setMapping({ ...mapping, [f]: e.target.value === "" ? "" : Number(e.target.value) })}>
                  <option value="">— skip</option>
                  {upload.headers.map((h, i) => (
                    <option key={i} value={i}>
                      {h}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="text-xs">
              <thead>
                <tr>
                  {upload.headers.map((h, i) => (
                    <th key={i} className="px-2 py-1 text-left font-medium" style={{ color: "var(--muted)" }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {upload.preview_rows.map((r, i) => (
                  <tr key={i} className="border-t" style={{ borderColor: "var(--line)" }}>
                    {upload.headers.map((_, j) => (
                      <td key={j} className="max-w-60 truncate px-2 py-1">
                        {r[j]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex justify-end">
            <button className="btn btn-accent" disabled={busy || mapping.caption === ""} onClick={() => step(() => call<Validation>(`${base}/validate`, { method: "POST", body: JSON.stringify({ mapping }) }), setValidation)}>
              Validate
            </button>
          </div>
        </Section>
      )}

      {validation && (
        <Section title="3. Review">
          <p className="text-sm">
            {validation.valid_count} of {validation.total_rows} rows will import.
          </p>
          {validation.errors.length > 0 && (
            <ul className="mt-2 max-h-60 space-y-1 overflow-y-auto text-xs" style={{ color: "var(--bad)" }}>
              {validation.errors.map((e) => (
                <li key={e.row}>
                  Row {e.row}: {e.errors.join("; ")}
                </li>
              ))}
              {validation.has_more_errors && <li>…and more</li>}
            </ul>
          )}
          <div className="mt-3 flex justify-end">
            <button className="btn btn-accent" disabled={busy || validation.valid_count === 0} onClick={() => step(() => call<Result>(`${base}/confirm`, { method: "POST" }), setResult)}>
              Import {validation.valid_count} posts
            </button>
          </div>
        </Section>
      )}
    </div>
  );
}
