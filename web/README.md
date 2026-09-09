# Osir Console

The human side of the Osir AI autopilot: what the agent did, what it needs you to decide, a box to ask it for something, and the autonomy dial. Next.js 15 (App Router, TypeScript, Tailwind 4) talking to Studio's `/api/v1/agent/*` REST API with one server-side API key.

```bash
cd web
cp .env.example .env.local     # STUDIO_URL + STUDIO_API_KEY
npm install
npm run dev                    # http://localhost:3000
```

Pages:

- `/` Ask Osir (command box), open decisions and digests, the autonomy dial, recent runs.
- `/approvals` drafts the agent submitted, with approve / reject.
- `/runs` and `/runs/[id]` every run with its structured report.

Commands typed here become `pending` runs in Studio. They are executed by Amazon Bedrock AgentCore when Studio has `AGENT_RUNTIME_ARN`, or by `python agent/run_local.py worker` on your machine.

The key needs `use_inbox`, `reply_from_inbox`, `create_posts`, `approve_posts`, `view_analytics`, and `manage_workspace_settings` (to move the dial). Everything the console does is attributed to the key's issuer, exactly like the agent's actions.
