# Deploy Osir AI — langkah demi langkah

Dua bagian, dideploy terpisah dan berurutan:

1. **Studio + console** (Django + Next.js + Postgres di belakang Caddy) di satu server Docker.
2. **Autopilot agent** di Amazon Bedrock AgentCore Runtime, dijadwalkan oleh EventBridge
   Scheduler, memanggil Studio lewat MCP.

Contoh di bawah memakai domain `app.osir.ai`, region AWS `us-west-2`, account id
`123456789012`. Ganti sesuai punyamu.

---

## Bagian 1 — Studio + console

### Langkah 1. Siapkan server

1. Buat VM Ubuntu 22.04/24.04, minimal 2 vCPU / 4 GB RAM / 40 GB disk (EC2 `t4g.medium`,
   Lightsail 4 GB, Hetzner CX22, dsb). Catat IP publiknya.
2. Buka port 22, 80, 443 di firewall/security group. Port lain tidak perlu.
3. Masuk lewat SSH dan pasang Docker:
   ```bash
   ssh ubuntu@<IP>
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER && newgrp docker
   docker compose version        # harus v2.x
   sudo apt-get install -y git make
   ```
4. DNS: buat record `A` `app.osir.ai → <IP>`. Tunggu sampai `dig +short app.osir.ai`
   mengembalikan IP itu. Caddy baru bisa mengambil sertifikat TLS setelah DNS resolve.

### Langkah 2. Ambil kode

```bash
git clone https://github.com/maulana-tech/osir-ai.git
cd osir-ai
cp .env.example .env
```

### Langkah 3. Isi `.env`

Buat dua nilai acak (jalankan dua kali):
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

Edit `.env` (`nano .env`). Minimal yang harus diisi:

```ini
# --- wajib ---
SECRET_KEY=<acak 1>
ENCRYPTION_KEY_SALT=<acak 2>       # JANGAN diganti setelah ada data: token OAuth dienkripsi dengan turunan ini
DEBUG=False
APP_DOMAIN=app.osir.ai             # dipakai Caddy + console
APP_URL=https://app.osir.ai        # dipakai untuk redirect URI OAuth, link email, MCP discovery
ALLOWED_HOSTS=app.osir.ai,app      # "app" = nama service di Compose (healthcheck internal)

# --- database & file: biarkan default, compose prod menimpanya ---
DATABASE_URL=postgres://postgres:postgres@localhost:5432/osir_ai
STORAGE_BACKEND=local
MEDIA_ROOT=/app/media

# --- email (undangan tim, magic link client portal, notifikasi) ---
EMAIL_BACKEND_TYPE=smtp
EMAIL_HOST=smtp.resend.com         # atau SES/Mailgun/Gmail
EMAIL_PORT=587
EMAIL_HOST_USER=resend
EMAIL_HOST_PASSWORD=re_xxx
EMAIL_USE_TLS=true
DEFAULT_FROM_EMAIL=noreply@osir.ai

# --- login Google (opsional) ---
GOOGLE_AUTH_CLIENT_ID=
GOOGLE_AUTH_CLIENT_SECRET=

# --- channel: isi yang dipakai, sisanya kosong ---
PLATFORM_LINKEDIN_PERSONAL_CLIENT_ID=
PLATFORM_LINKEDIN_PERSONAL_CLIENT_SECRET=
PLATFORM_FACEBOOK_APP_ID=
PLATFORM_FACEBOOK_APP_SECRET=
# ...lihat .env.example untuk platform lain

# --- fallback OAuth via Composio (kalau tidak punya developer app sendiri) ---
COMPOSIO_API_KEY=
COMPOSIO_AUTH_CONFIG_LINKEDIN=
COMPOSIO_AUTH_CONFIG_FACEBOOK=

# --- opsional ---
UNSPLASH_ACCESS_KEY=

# --- agen: diisi di Bagian 2 ---
AGENT_RUNTIME_ARN=
AGENT_RUNTIME_REGION=us-west-2
STUDIO_API_KEY=                    # hanya untuk agent-worker lokal (profile "agent"), bukan untuk AgentCore
```

Kalau ingin file media di S3/Cloudflare R2 (disarankan untuk produksi, supaya bisa
di-scale dan di-backup terpisah): `STORAGE_BACKEND=s3`, isi `S3_ENDPOINT_URL`,
`S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME`, `S3_REGION_NAME`
(`auto` untuk R2), dan bila ada `S3_CUSTOM_DOMAIN`.

Amankan file-nya: `chmod 600 .env`. File ini tidak masuk git; simpan salinan di password
manager.

### Langkah 4. Jalankan

```bash
make docker-prod
# sama dengan: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```
Build pertama 5–10 menit (image Django + Tailwind, image Next.js). Pantau:
```bash
docker compose ps                              # semua "running", migrate "exited (0)"
docker compose logs -f caddy                   # tunggu "certificate obtained successfully"
docker compose logs -f app worker console
```
Service yang jalan:

| Service | Fungsi |
|---|---|
| `postgres` | database (volume `postgres_data`) |
| `migrate` | `manage.py migrate`, jalan sekali sebelum `app`/`worker` |
| `app` | Django (gunicorn) di port internal 8000 |
| `worker` | `manage.py process_tasks` — publish, sinkron inbox, analytics. **Tanpa ini tidak ada yang terbit.** |
| `console` | Next.js di port internal 3000 |
| `caddy` | TLS + routing: path Django (`/api/*`, `/accounts/*`, `/social-accounts/*`, `/webhooks/*`, `/portal/*`, `/workspace/*`, …) → `app`, sisanya → `console` |

### Langkah 5. Akun pertama

```bash
docker compose exec app python manage.py createsuperuser
```
Buka `https://app.osir.ai/accounts/login/`, masuk. Organisasi + workspace dibuat otomatis.
Anggota lain bisa daftar sendiri di `/accounts/signup/` atau diundang dari console
(**Settings → Team → Invite**).

### Langkah 6. Hubungkan channel

Untuk tiap platform yang dipakai:
1. Di developer console platform tersebut, daftarkan redirect URI
   `https://app.osir.ai/social-accounts/callback/<platform>/`
   (`<platform>` = `linkedin_personal`, `facebook`, `instagram`, `youtube`, `tiktok`,
   `pinterest`, dsb; detail dan scope per platform ada di README bagian "Platform Credentials").
2. Untuk webhook inbox real-time: Meta → `https://app.osir.ai/webhooks/facebook/` dan
   `/webhooks/instagram_login/` dengan verify token dari `.env`; YouTube → `/webhooks/youtube/`.
3. Di console: **Channels → Connect**, pilih platform, selesaikan OAuth.
   Kalau developer app kosong tapi `COMPOSIO_AUTH_CONFIG_<PLATFORM>` terisi, tombolnya
   otomatis menjadi "Connect via Composio".

### Langkah 7. Verifikasi

```bash
curl -s https://app.osir.ai/health/                       # {"status": "ok"} / 200
curl -sI https://app.osir.ai/ | head -1                   # 302 ke /accounts/login/ atau /w/...
docker compose exec app python manage.py check --deploy   # tidak boleh ada WARNING keamanan
```
Di browser: login → calendar → **New post** → simpan draft → **Media** upload gambar →
**Channels** terhubung → jadwalkan satu post dan pastikan `worker` menerbitkannya
(`docker compose logs -f worker`).

### Langkah 8. Operasional

```bash
# update ke versi baru
git pull && make docker-prod

# backup
docker compose exec -T postgres pg_dump -U postgres osir_ai | gzip > backup-$(date +%F).sql.gz
docker run --rm -v osir-ai_media_data:/data -v $PWD:/out alpine tar czf /out/media-$(date +%F).tgz /data

# restore db
gunzip -c backup-YYYY-MM-DD.sql.gz | docker compose exec -T postgres psql -U postgres osir_ai

# log
docker compose logs -f --tail=200 app worker console caddy
```
Jadwalkan backup harian dengan cron. Kalau memakai S3/R2, cukup backup database.

---

## Bagian 2 — Autopilot agent di Bedrock AgentCore

### Langkah 1. Prasyarat di laptop

```bash
aws --version                      # AWS CLI v2
aws configure                      # atau AWS_PROFILE; region us-west-2
aws sts get-caller-identity        # harus mengembalikan account id-mu
docker buildx version              # image AgentCore wajib linux/arm64
jq --version
node --version                     # 20+
npm install -g @aws/agentcore
```
Model access: AWS console → Bedrock → *Model access* → aktifkan Anthropic Claude di region
yang dipakai. Default agen adalah `global.anthropic.claude-sonnet-4-6`
(`agent/osir_agent/config.py`); ganti dengan env `BEDROCK_MODEL_ID` kalau perlu.

### Langkah 2. API key untuk agen

Di console Studio: **Settings → API keys → Issue a key**.
- Workspace: yang mau diurus agen.
- Accounts: semua channel yang boleh disentuh (allowlist keras; agen tidak bisa melihat
  channel di luar ini).
- Permissions: `use_inbox`, `reply_from_inbox`, `create_posts`, `view_analytics`,
  `manage_workspace_settings`. Tambah `publish_directly` hanya kalau level `autopilot`
  boleh menjadwalkan sendiri.
- Token `bb_studio_...` hanya ditampilkan sekali. Simpan.

### Langkah 3. Uji agen dari laptop dulu

```bash
cd agent
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export STUDIO_URL=https://app.osir.ai
export STUDIO_API_KEY=bb_studio_...
export AWS_REGION=us-west-2

python run_local.py inbox --dry-run      # membaca inbox, tidak menulis apa pun
python run_local.py digest               # mengirim ringkasan ke notifikasi
python run_local.py command "Rangkum performa minggu lalu"
```
Kalau ini gagal (401 → key/permission; 403 → channel di luar allowlist; error Bedrock →
model access/region), perbaiki sebelum deploy.

### Langkah 4. Build dan push image agen (arm64)

```bash
cd agent
export AWS_REGION=us-west-2 ACCOUNT=123456789012
aws ecr create-repository --repository-name osir-agent >/dev/null 2>&1 || true
aws ecr get-login-password | docker login --username AWS --password-stdin $ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com
docker buildx build --platform linux/arm64 \
  -t $ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/osir-agent:latest --push .
```
Image menjalankan `main.py` (`BedrockAgentCoreApp`): port 8080, endpoint `/invocations`
dan `/ping`.

### Langkah 5. IAM role untuk runtime

Runtime butuh role yang bisa memanggil Bedrock dan menulis log. Simpan sebagai
`runtime-trust.json`:
```json
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"bedrock-agentcore.amazonaws.com"},"Action":"sts:AssumeRole"}]}
```
dan `runtime-policy.json`:
```json
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":["bedrock:InvokeModel","bedrock:InvokeModelWithResponseStream"],"Resource":"*"},
 {"Effect":"Allow","Action":["ecr:GetAuthorizationToken","ecr:BatchGetImage","ecr:GetDownloadUrlForLayer"],"Resource":"*"},
 {"Effect":"Allow","Action":["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents","logs:DescribeLogGroups","logs:DescribeLogStreams"],"Resource":"*"},
 {"Effect":"Allow","Action":["xray:PutTraceSegments","xray:PutTelemetryRecords"],"Resource":"*"}
]}
```
```bash
aws iam create-role --role-name osir-agent-runtime --assume-role-policy-document file://runtime-trust.json
aws iam put-role-policy --role-name osir-agent-runtime --policy-name osir-agent-runtime --policy-document file://runtime-policy.json
```

### Langkah 6. Buat runtime

Pilihan A — AgentCore CLI (mengikuti `agent/README.md`):
```bash
cd agent
agentcore create --project-name osir --name osir-agent --language Python \
  --framework Strands --model-provider Bedrock --build Container
# arahkan agentcore.json ke Dockerfile folder ini (atau salin main.py, osir_agent/, requirements.txt ke app/ hasil generate)
agentcore deploy
```

Pilihan B — AWS CLI langsung dengan image dari Langkah 4:
```bash
aws bedrock-agentcore-control create-agent-runtime \
  --agent-runtime-name osir_agent \
  --agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"$ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/osir-agent:latest\"}}" \
  --network-configuration '{"networkMode":"PUBLIC"}' \
  --role-arn arn:aws:iam::$ACCOUNT:role/osir-agent-runtime \
  --environment-variables STUDIO_URL=https://app.osir.ai,STUDIO_API_KEY=bb_studio_...,BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-4-6
```
Output berisi `agentRuntimeArn` seperti
`arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/osir_agent-AbCdEf1234`. Catat.
Tunggu status `READY`:
```bash
aws bedrock-agentcore-control get-agent-runtime --agent-runtime-id osir_agent-AbCdEf1234 --query status
```
Lebih aman menyimpan `STUDIO_API_KEY` sebagai AgentCore Identity API-key credential
provider daripada env var polos; env var cukup untuk demo hackathon.

### Langkah 7. Uji invoke

```bash
ARN=arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/osir_agent-AbCdEf1234
aws bedrock-agentcore invoke-agent-runtime --agent-runtime-arn $ARN \
  --runtime-session-id "osir-test-$(date +%s)-session-0000000000000" \
  --payload '{"task":"inbox","dry_run":true}' /dev/stdout
```
(`runtimeSessionId` minimal 33 karakter.) Payload lain: `{"task":"calendar"}`,
`{"task":"digest"}`, `{"task":"command","instruction":"Plan next week for LinkedIn"}`.
Dengan CLI AgentCore: `agentcore invoke --prompt '...'`.

Log ada di CloudWatch, log group `/aws/bedrock-agentcore/runtimes/<runtime-id>-DEFAULT`.

### Langkah 8. Sambungkan Studio ke runtime

Studio memanggil `InvokeAgentRuntime` saat seseorang mengetik perintah di
**Autopilot → Ask Osir** (`apps/autopilot/tasks.py`). Di server Studio:

1. Kredensial AWS untuk container `app` dan `worker`. Kalau server di EC2: pasang instance
   role dengan policy berikut. Kalau di luar AWS: buat IAM user dengan policy ini dan
   tambahkan `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION=us-west-2`
   ke `.env`.
   ```json
   {"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"bedrock-agentcore:InvokeAgentRuntime","Resource":"arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/osir_agent-AbCdEf1234*"}]}
   ```
2. Di `.env`:
   ```ini
   AGENT_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/osir_agent-AbCdEf1234
   AGENT_RUNTIME_REGION=us-west-2
   ```
3. `make docker-prod` (restart dengan env baru).
4. Uji: console → **Autopilot → Ask Osir** → ketik "Ringkas inbox hari ini" → run muncul di
   **Runs** dan berubah dari `pending` ke `succeeded`.

Tanpa `AGENT_RUNTIME_ARN`, perintah hanya menunggu worker lokal
(`docker compose --profile agent up -d` dengan `STUDIO_API_KEY` di `.env`) — berguna untuk
demo tanpa AWS.

### Langkah 9. Jadwal otomatis (EventBridge Scheduler)

Role untuk Scheduler — `scheduler-trust.json`:
```json
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"scheduler.amazonaws.com"},"Action":"sts:AssumeRole"}]}
```
`scheduler-policy.json`:
```json
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"bedrock-agentcore:InvokeAgentRuntime","Resource":"arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/osir_agent-AbCdEf1234*"}]}
```
```bash
aws iam create-role --role-name osir-scheduler --assume-role-policy-document file://scheduler-trust.json
aws iam put-role-policy --role-name osir-scheduler --policy-name invoke-osir-agent --policy-document file://scheduler-policy.json

cd agent
AGENT_RUNTIME_ARN=$ARN \
SCHEDULER_ROLE_ARN=arn:aws:iam::123456789012:role/osir-scheduler \
./schedule/create_schedules.sh
```
Skrip membuat grup `osir-agent` dengan tiga jadwal:

| Nama | Ekspresi | Task |
|---|---|---|
| `osir-inbox` | `rate(15 minutes)` | balas/triage inbox |
| `osir-calendar` | `cron(0 7 * * ? *)` (07:00 UTC harian) | isi kalender dengan draf |
| `osir-digest` | `cron(0 8 ? * MON *)` (Senin 08:00 UTC) | ringkasan mingguan |

Ubah jam di skrip sesuai zona waktu tim (mis. WIB = UTC+7 → 07:00 WIB = `cron(0 0 * * ? *)`).
Cek: `aws scheduler list-schedules --group-name osir-agent`.

### Langkah 10. Verifikasi dan pengaturan awal

- **Autopilot → Runs** di console: setiap jadwal menghasilkan run dengan laporan
  (`actions`, `decisions_for_humans`, `notes`).
- **Workspace settings → Osir AI autopilot**: mulai di `draft_only` (agen membalas inbox
  rutin dan membuat draf yang masuk antrean approval). Naikkan ke `autopilot` setelah
  beberapa hari kalau drafnya oke; `off` untuk menghentikan tanpa mencabut jadwal.
- Eskalasi dan digest muncul sebagai notifikasi biasa (**Notifications**), termasuk email
  sesuai preferensi.

### Membersihkan (kalau perlu)

```bash
aws scheduler delete-schedule --group-name osir-agent --name osir-inbox   # dst
aws bedrock-agentcore-control delete-agent-runtime --agent-runtime-id osir_agent-AbCdEf1234
```

---

## Troubleshooting

| Gejala | Penyebab umum | Perbaikan |
|---|---|---|
| Caddy tidak dapat sertifikat | DNS belum resolve / port 80 tertutup | `dig +short app.osir.ai`, buka port 80, `docker compose restart caddy` |
| Login 400 "CSRF verification failed" | `APP_URL`/`ALLOWED_HOSTS` tidak cocok dengan domain | samakan keduanya dengan domain di browser, restart `app` |
| Console 502 lewat Caddy | container `console` belum selesai build/start | `docker compose logs console` |
| Post tidak terbit | `worker` mati | `docker compose ps`, `docker compose logs worker` |
| OAuth "redirect URI mismatch" | URI di platform ≠ `APP_URL` + `/social-accounts/callback/<platform>/` | samakan persis (https, tanpa port) |
| Agen 401 ke Studio | `STUDIO_API_KEY` salah/revoked | issue key baru, update env runtime |
| Agen error Bedrock `AccessDenied` | model access belum aktif / role runtime tanpa `bedrock:InvokeModel` | aktifkan model access di region, cek policy Langkah 5 |
| Perintah di console tetap `pending` | `AGENT_RUNTIME_ARN` kosong atau container Studio tanpa kredensial AWS | cek `.env`, `docker compose logs worker` |
| Jadwal tidak memicu | role scheduler tanpa izin invoke | cek policy Langkah 9, `aws scheduler get-schedule` |

## Checklist

- [ ] Server + Docker + DNS + port 80/443
- [ ] `.env`: SECRET_KEY, ENCRYPTION_KEY_SALT, DEBUG=False, APP_DOMAIN, APP_URL, ALLOWED_HOSTS, SMTP
- [ ] `make docker-prod`, sertifikat TLS didapat, `/health/` 200
- [ ] Superuser dibuat, login berhasil
- [ ] Redirect URI + webhook terdaftar, channel terhubung, satu post terbit
- [ ] API key agen dibuat, `run_local.py inbox --dry-run` sukses
- [ ] Image arm64 di ECR, role runtime, runtime READY, invoke sukses
- [ ] `AGENT_RUNTIME_ARN` + kredensial AWS di Studio, perintah dari console jalan
- [ ] Role scheduler, `create_schedules.sh`, run terjadwal muncul
- [ ] Dial autopilot diset (`draft_only` dulu)
