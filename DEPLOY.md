# Deploy Osir AI

Dua bagian yang di-deploy terpisah:

1. **Studio + console** (Django + Next.js + Postgres di belakang Caddy) di satu server
   Docker — VPS apa saja (EC2, Lightsail, Hetzner, DigitalOcean).
2. **Autopilot agent** di Amazon Bedrock AgentCore Runtime, dijadwalkan lewat
   EventBridge Scheduler, memanggil Studio lewat MCP.

Urutannya: Studio dulu (agen butuh URL publik + API key dari Studio).

---

## Bagian 1 — Studio + console (Docker + Caddy)

### 1.1 Siapkan server
- Ubuntu 22.04+/Debian, 2 vCPU, 4 GB RAM cukup untuk mulai. Docker Engine + Compose plugin
  terpasang (`docker compose version`).
- Port 80 dan 443 terbuka. DNS `A` record domain kamu (mis. `app.osir.ai`) mengarah ke IP
  server. Caddy mengurus sertifikat TLS otomatis (Let's Encrypt) — tidak perlu certbot.

### 1.2 Ambil kode dan buat `.env`
```bash
git clone https://github.com/maulana-tech/osir-ai.git && cd osir-ai
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # jalankan 2x untuk dua nilai di bawah
```
Isi minimum di `.env`:

| Kunci | Nilai |
|---|---|
| `SECRET_KEY`, `ENCRYPTION_KEY_SALT` | dua string acak dari perintah di atas. **Jangan pernah diganti setelah ada data** — token OAuth dienkripsi dengan turunan keduanya. |
| `DEBUG` | `False` |
| `APP_DOMAIN` | `app.osir.ai` (dipakai Caddy dan console) |
| `APP_URL` | `https://app.osir.ai` (dipakai untuk OAuth redirect URI, link email, MCP discovery) |
| `ALLOWED_HOSTS` | `app.osir.ai,app` (`app` = nama service di Compose; console memanggil Django lewat Caddy, tapi healthcheck internal pakai nama service) |
| `DATABASE_URL` | biarkan — `docker-compose.prod.yml` menimpanya ke Postgres internal |
| `STORAGE_BACKEND` / `MEDIA_ROOT` | `local` + `/app/media` (volume `media_data`); untuk S3/R2 lihat README bagian storage |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL` | SMTP untuk undangan tim, magic link client portal, notifikasi |
| `PLATFORM_*` | kredensial developer app per platform yang ingin dipakai (boleh kosong dulu) |
| `COMPOSIO_API_KEY`, `COMPOSIO_AUTH_CONFIG_*` | fallback OAuth via Composio kalau tidak punya developer app sendiri |
| `UNSPLASH_ACCESS_KEY` | opsional, untuk pencarian foto di composer |
| `AGENT_RUNTIME_ARN`, `AGENT_RUNTIME_REGION` | isi nanti di Bagian 2 |

Catatan: `.env` tidak masuk git. Simpan salinannya di tempat aman.

### 1.3 Jalankan
```bash
make docker-prod
# = docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose logs -f app console caddy     # tunggu sampai Caddy dapat sertifikat
```
Yang jalan: `postgres`, `migrate` (sekali, lalu selesai), `app` (gunicorn), `worker`
(`process_tasks` — tanpa ini tidak ada yang terbit), `console` (Next.js), `caddy`.
Caddy merutekan `/api/*`, `/accounts/*`, `/social-accounts/*`, `/webhooks/*`, `/portal/*`,
`/workspace/*` dll. ke Django dan sisanya ke console (lihat `Caddyfile`).

### 1.4 Buat akun pertama
```bash
docker compose exec app python manage.py createsuperuser
```
Lalu buka `https://app.osir.ai/accounts/login/`. Signup biasa juga bisa lewat
`/accounts/signup/` (organisasi + workspace dibuat otomatis).

### 1.5 Daftarkan redirect URI di tiap platform
Setiap developer app harus mengizinkan `https://app.osir.ai/social-accounts/callback/<platform>/`
(detail per platform di README bagian "Platform Credentials"). Webhook Meta/YouTube
menunjuk ke `https://app.osir.ai/webhooks/...`. Setelah itu hubungkan channel dari
console: **Channels → Connect**.

### 1.6 Verifikasi
```bash
curl -s https://app.osir.ai/health/                      # 200
curl -sI https://app.osir.ai/ | head -1                  # 200/302 dari console
docker compose exec app python manage.py check --deploy
```
Cek di browser: login, calendar, compose (simpan draft), media upload, channels.

### 1.7 Update
```bash
git pull
make docker-prod        # rebuild image, migrate jalan otomatis sebelum app/worker start
```
Backup: `docker compose exec postgres pg_dump -U postgres osir_ai > backup.sql` plus volume
`media_data`.

---

## Bagian 2 — Autopilot agent di Bedrock AgentCore

### 2.1 Prasyarat
- AWS CLI v2 terkonfigurasi (`aws sts get-caller-identity` berhasil) di region yang
  mendukung AgentCore (mis. `us-west-2`, `us-east-1`).
- Model access di Bedrock untuk Claude (default agen: `global.anthropic.claude-sonnet-4-6`,
  ubah lewat env `BEDROCK_MODEL_ID`).
- Docker dengan buildx (image AgentCore harus `linux/arm64`).
- `jq` untuk `schedule/create_schedules.sh`.
- Node 20+ untuk AgentCore CLI: `npm install -g @aws/agentcore`.

### 2.2 Buat API key di Studio
Di console: **Settings → API keys → Issue a key**. Pilih workspace, semua akun yang boleh
disentuh agen, dan permission `use_inbox`, `reply_from_inbox`, `create_posts`,
`view_analytics`, `manage_workspace_settings`; tambah `publish_directly` hanya kalau
ingin level `autopilot` bisa menjadwalkan sendiri. Token (`bb_studio_...`) hanya
ditampilkan sekali — simpan.

Uji dari laptop sebelum deploy:
```bash
cd agent
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
export STUDIO_URL=https://app.osir.ai STUDIO_API_KEY=bb_studio_...
export AWS_REGION=us-west-2          # kredensial AWS via env/profile
python run_local.py inbox --dry-run  # harus bisa membaca inbox tanpa mengubah apa pun
python run_local.py digest
```

### 2.3 Deploy runtime
Dari folder `agent/`:
```bash
agentcore create --project-name osir --name osir-agent --language Python \
  --framework Strands --model-provider Bedrock --build Container
```
Perintah ini membuat proyek + `agentcore.json`. Arahkan build-nya ke `agent/Dockerfile`
yang sudah ada (atau salin `main.py`, `osir_agent/`, `requirements.txt` ke folder app yang
dibuat CLI). Entrypoint-nya `main.py` (`BedrockAgentCoreApp`, port 8080, `/invocations`
dan `/ping`).

Set environment variable runtime: `STUDIO_URL`, `STUDIO_API_KEY` (lebih aman: simpan
sebagai AgentCore Identity API-key credential provider), opsional `BEDROCK_MODEL_ID`.

```bash
agentcore deploy
agentcore invoke --prompt 'Plan next week for the LinkedIn page'   # prompt polos = mode command
agentcore invoke --payload '{"task":"inbox","dry_run":true}'
```
Catat ARN runtime dari output deploy (`arn:aws:bedrock-agentcore:<region>:<acct>:runtime/osir-agent-xxxx`).

Kalau lebih suka tanpa CLI: `docker buildx build --platform linux/arm64 -t osir-agent .`,
push ke ECR, lalu `aws bedrock-agentcore-control create-agent-runtime` dengan image itu dan
env var yang sama.

### 2.4 Sambungkan Studio ke runtime
Di `.env` server Studio:
```
AGENT_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/osir-agent-xxxx
AGENT_RUNTIME_REGION=us-west-2
```
Container `app`/`worker` butuh kredensial AWS dengan izin `bedrock-agentcore:InvokeAgentRuntime`
pada ARN itu (IAM role instance, atau `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` di `.env`).
Lalu `make docker-prod` lagi. Sejak itu perintah yang diketik di **Autopilot → Ask Osir**
dikirim ke AgentCore; tanpa ARN, perintah menunggu `agent/run_local.py worker`.

### 2.5 Jadwal (EventBridge Scheduler)
Buat IAM role untuk Scheduler: trust policy `scheduler.amazonaws.com`, permission
`bedrock-agentcore:InvokeAgentRuntime` pada ARN runtime. Lalu:
```bash
cd agent
AGENT_RUNTIME_ARN=arn:aws:bedrock-agentcore:...:runtime/osir-agent-xxxx \
SCHEDULER_ROLE_ARN=arn:aws:iam::123456789012:role/osir-scheduler \
./schedule/create_schedules.sh
```
Membuat tiga jadwal di grup `osir-agent`: `osir-inbox` tiap 15 menit, `osir-calendar`
harian 07:00 UTC, `osir-digest` Senin 08:00 UTC. Ubah ekspresi cron di skrip kalau
zona waktu tim berbeda.

### 2.6 Verifikasi
- **Autopilot → Runs** di console menampilkan run baru per jadwal, dengan laporan
  (actions, decisions_for_humans).
- Set dial di **Workspace settings → Osir AI autopilot** ke `draft_only` dulu; naikkan ke
  `autopilot` setelah beberapa hari melihat drafnya.
- Log runtime: CloudWatch log group AgentCore untuk `osir-agent`; log Studio:
  `docker compose logs -f app worker`.

---

## Checklist singkat
- [ ] DNS → server, port 80/443 terbuka
- [ ] `.env` terisi (SECRET_KEY, ENCRYPTION_KEY_SALT, APP_DOMAIN, APP_URL, ALLOWED_HOSTS, SMTP)
- [ ] `make docker-prod`, `/health/` 200, login berhasil
- [ ] Redirect URI + webhook terdaftar di platform, channel terhubung
- [ ] API key untuk agen dibuat, `run_local.py inbox --dry-run` jalan
- [ ] `agentcore deploy`, ARN dicatat, `agentcore invoke` sukses
- [ ] `AGENT_RUNTIME_ARN` di `.env` Studio + kredensial AWS, redeploy
- [ ] `create_schedules.sh`, run muncul di console
