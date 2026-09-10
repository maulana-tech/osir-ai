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

### 1. Hapus UI Django lama (template + view)
Template dan view Django untuk halaman-halaman di atas masih ada di `templates/` dan
`apps/*/views.py`, tetapi sudah tidak dipakai console. Rencana yang belum dijalankan:

- Ganti view halaman dengan `apps.common.console.console("/w/{workspace_id}/...")` di
  masing-masing `urls.py` agar nama URL tetap hidup untuk `reverse()` di email/notifikasi,
  lalu hapus fungsi view dan folder template-nya:
  `templates/{calendar,composer,media_library,inbox,analytics,members,notifications,approvals,organizations,workspaces,api_keys,settings_manager}`,
  `templates/accounts/{dashboard,settings}.html`, `templates/social_accounts/list.html`.
- Hapus endpoint HTMX/JSON yang fungsinya sudah ada di `/api/web/`
  (kecuali yang masih dipakai console: `composer.media_stream`, `composer.media_filmstrip`,
  `media_library.asset_download`, `media_library_org.shared_asset_download`,
  `members.accept_invite`, semua OAuth connect/callback/reconnect di `social_accounts`, webhooks).
- Putuskan nasib `templates/base.html`, `layouts/`, `components/`, `partials/` dan
  `apps/common/context_processors.py:sidebar_context` (hanya perlu jika masih ada template
  yang meng-extend `base.html`).
- `/` (dashboard Django) → redirect ke `/w/<last_workspace_id>/calendar`.
- ~82 test yang bergantung pada halaman lama harus di-port ke service atau ke route
  `/api/web/` (lihat `apps/webapi/tests/`), bukan sekadar dihapus. Daftar file:
  `apps/api_keys/tests/test_views.py`, `apps/analytics/tests/test_views.py`,
  `apps/calendar/test_bulk_actions.py`, `apps/calendar/tests.py`,
  `apps/members/tests/test_role_hierarchy.py`, `apps/inbox/tests/test_send_reply.py`,
  `apps/approvals/test_workflow.py`, `apps/approvals/test_security.py`,
  `apps/notifications/tests.py`, `apps/media_library/tests/*`,
  `apps/composer/tests/{test_account_scope,test_proposed_publish_at,test_save_post_tags,test_idea_media_flows,test_unsplash,test_template_picker,test_csv_upload_size,test_preview}.py`,
  `apps/api/tests/test_review_fixes_round2.py`.
- Setelah itu kecilkan daftar path yang diproksi ke Django di `web/next.config.ts`
  (`DJANGO_PATHS`) dan `Caddyfile` (`@django`).

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
`CLAUDE.md` bagian "What this is" masih menyebut "Server-rendered templates + HTMX" —
perbarui setelah UI Django dihapus. `README.md` bagian docker/prod sudah diperbarui.
