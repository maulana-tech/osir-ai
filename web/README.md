# Osir AI web UI

The Next.js 15 (App Router, TypeScript, Tailwind 4) frontend for Osir AI. Django stays the backend; this app replaces its templates page by page.

```bash
cd web
cp .env.example .env.local     # STUDIO_URL (default http://localhost:8000)
npm install
npm run dev                    # http://localhost:3000
```

Sign in at http://localhost:3000/accounts/login/ — the dev server proxies Django's auth, API, OAuth and not-yet-migrated pages, so there is one origin and one session cookie.

Pages:

- `/w/[workspace]/calendar` month / week / day / list with drag-to-reschedule, `/inbox` (+ `/inbox/settings`), `/analytics`, `/approvals` (approve, reject, request changes, resume holds, bulk, comments, version diff), `/channels` (connect, reconnect, disconnect, webhook retry), `/settings` (general, approval mode, autopilot dial, logo, client portal, archive / delete).
- `/w/[workspace]/media` the media library: folders, search and filters, drag-and-drop upload with progress, starring, tags, versions, and an image (crop / rotate / flip) and video (trim) editor. `/org/media` is the organization's shared library.
- `/w/[workspace]/agent` the autopilot console: command box, decisions, digests, runs and their reports.
- `/org/settings`, `/org/workspaces`, `/org/members` (invites, roles, per-workspace access), `/org/api-keys` (issue with one-time token reveal, edit scope, revoke).
- `/me/account`, `/me/notifications`, `/me/notifications/preferences`.

Still served by Django and proxied: composer (`/workspace/...`), login / signup / 2FA, OAuth connect, client portal, onboarding tokens.

How it talks to Studio: server components call `/api/web/` and `/api/v1/agent/*` with the browser's session cookie (`lib/studio.ts`); client components mutate through `lib/client.ts`, which echoes Django's CSRF token. Everything is attributed to the signed-in person. Commands typed in the console become `pending` runs, executed by Amazon Bedrock AgentCore when Studio has `AGENT_RUNTIME_ARN`, or by `python agent/run_local.py worker` locally.
