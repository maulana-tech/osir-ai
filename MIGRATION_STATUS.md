# Status migrasi frontend ke Next.js (TSX)

Backend tetap Django. Semua halaman aplikasi sudah dirender oleh console Next.js di `web/`
dan berbicara ke JSON API ber-sesi di `/api/web/` (`apps/webapi/`). Dokumen ini mencatat
apa yang **belum** selesai.

## Sudah selesai

- Shell (sidebar, workspace switcher, onboarding checklist), login via sesi Django.
- Calendar: month/week/day/list, drag-to-reschedule, custom events, selection bar
  (unschedule / publish now / delete), posting slots, queues (reorder, remove, next open slot).
- Composer: `/w/[ws]/compose` dan `/compose/[id]` (channel chips + transisi status per akun,
  caption + counter per platform, media dari library/upload/Unsplash, override per channel,
  panel YouTube/Pinterest/TikTok, preview, schedule + recurrence + queue, semua aksi simpan,
  autosave 30 detik, clone, save as template, hapus).
- Create: ideas kanban, template gallery, RSS feeds + explore; Categories; CSV import.
- Inbox (+ settings), Analytics (+ drawer per post), Approvals (request changes, resume,
  bulk, comments, version diff), Channels, Media library (+ editor gambar/video), shared media org.
- Settings workspace, organisasi, workspaces, kalender lintas workspace, tim, API keys,
  akun, notifikasi + preferensi.

## Belum selesai

### 1. Hapus UI Django lama (template + view) — SELESAI
Template dan view Django untuk halaman yang sudah pindah telah dihapus. URL lamanya
menjadi redirect `apps.common.console.console(...)` ke halaman console (nama URL tetap
hidup untuk `reverse()` di email/notifikasi). Yang masih view Django asli: endpoint file
(`media_library.asset_download`, `shared_asset_download`, `composer.media_stream`,
`composer.media_filmstrip`), `members.accept_invite`, semua OAuth di `social_accounts`,
webhooks, client portal, onboarding, auth (allauth). Test lama sudah di-port ke service
atau ke route `/api/web/` (`apps/webapi/tests/`).

Sisa yang masih bisa dirapikan:
- `templates/base.html`, `layouts/`, `components/`, `partials/`, `social_accounts/partials/`
  masih dipakai halaman auth/OAuth/onboarding, jadi dipertahankan. Bisa disederhanakan
  (sidebar lama, `sidebar_context`) kalau halaman-halaman itu ikut dipindah ke console.
- Daftar path yang diproksi ke Django di `web/next.config.ts` (`DJANGO_PATHS`) dan
  `Caddyfile` (`@django`) sengaja masih memuat `/workspace/`, `/organizations/media/`,
  `/members/`, `/workspaces/`, `/notifications/` dll. karena Django yang mengalihkan URL
  lama itu ke console; boleh dikecilkan kalau redirect lama tidak diperlukan lagi.

### 2. Halaman yang sengaja masih Django
Login/signup/2FA/reset password (allauth), OAuth connect + callback, client portal,
halaman token onboarding, halaman terima undangan. Ini boleh tetap Django; kalau ingin
100% TSX, masing-masing butuh route API + halaman baru.

### 3. Fitur yang disederhanakan di versi TSX
- TikTok cover frame: input detik (bukan filmstrip picker). Endpoint filmstrip masih ada.
- Cropper gambar: drag-select buatan sendiri (tanpa Cropper.js); rotasi/flip lewat preview.
- Analytics post detail dari URL Django lama (`/analytics/post/<id>/`) mendarat di index analytics
  karena URL lama tidak membawa account id.
- Notification drawer/unread badge di header belum ada di console (halaman notifikasi ada).

### 4. Verifikasi manual
Semua halaman sudah dicek 200 lewat curl dan `npm run build` bersih, tetapi belum diklik
di browser dengan akun asli (login tidak bisa diotomasi). Cek terutama: composer
(simpan/schedule/queue), media editor, kanban drag-and-drop, calendar selection bar.

### 5. Dokumen
`CLAUDE.md`, `README.md` dan `web/README.md` sudah menggambarkan console sebagai UI utama.
