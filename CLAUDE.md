# Kanalchi — working notes for Claude Code

Multi-tenant "AI helper for Telegram bloggers". One deployment serves many channels; tenant = Host header.
Roles: viewer (public), blogger (`/studio`, Telegram Login + channel-admin check), admin (ADMIN_HOST, allowlist),
user (signed in on PLATFORM_DOMAIN `/start` to register a channel: `api/routers/signup.py`, plans in `core/billing.py`).
Plans: archive (snapshot site) · basic (+ live updates) · premium (+ studio writing tools); payment is by hand in `/admin`.

## Layout
- `backend/kanalchi/` — Python 3.12, uv. `core/` settings+db+models+crypto+pricing, `telegram/` Telethon pool + aiogram bots,
  `ai/` Claude/Voyage (extraction, taxonomy, chat, drafting), `search/` hybrid search, `api/` FastAPI, `jobs/` procrastinate.
- `web/` — Next.js 16 (App Router). `proxy.ts` rewrites tenant hosts to `/t/[tenant]/…` and ADMIN_HOST to `/admin/…`.
- `infra/` — compose.yml (prod, all-in-Docker), compose.dev.yml (local infra only), Caddyfile (on-demand TLS via `/internal/tls/ask`).

## Invariants (do not break)
- A Telethon session is used by exactly one process: `worker-telegram`. All MTProto work is a job on queue `telegram`.
- Every tenant-owned query goes through `kanalchi.core.repo.scoped(Model, tenant_id)`.
- Bulk LLM work uses the Message Batches API (`claude-sonnet-5`); interactive work uses `claude-opus-5` with adaptive
  thinking, `output_config.effort`, prompt caching (stable prefix first, `cache_control` on the last stable block),
  streaming, structured outputs. No assistant prefill, no `budget_tokens`. Record every `usage` in `usage_ledger`.
- Long jobs are chains of short resumable jobs (≤ ~10 min). Backfill checkpoints on `channels.backfill_checkpoint`.
- Secrets at rest (Telethon sessions, bot tokens) are Fernet-encrypted (`core/crypto.py`); the API never decrypts sessions.
- `APP_ENV=prod` is what makes a deployment production: dev-login off, `APP_MASTER_KEY` + a real `SESSION_SECRET`
  required at startup, Secure cookies. `infra/compose.yml` sets it; never remove it from `infra/.env`.
- Presigned MinIO URLs are minted against the internal endpoint; anything a browser must open goes through
  `storage.public_presigned_url()` (Caddy proxies `/media/*` and `/uploads/*` to MinIO on every tenant host).

## Commands
`make dev-infra && make migrate && make seed && make api` (:8001) · `kanalchi seed-dev --posts 24` for synthetic posts · `make web` (:3001) · `make worker-*` ·
`make migration m="msg"` · `make test` · `make lint`. Dev ports are offset (5433/6380/9002/8443) to avoid collisions.

## Phase status
Phases 0-5 are in: scaffold, ingestion + public blog, extraction/taxonomy/tags, viewer chat,
blogger studio, admin ops + enrichment (stories, entity summaries, costs, alerts).
Model calls are unit-tested with fakes; whether they run for real depends on the keys in `backend/.env`
(anything that defers an AI job spends money when they are present). `kanalchi seed-dev --posts N` and `kanalchi seed-tags` give you demo content
and a hand-made taxonomy, which is enough to work on search, tags and every page without keys.

## Conventions
- Timestamps are tz-aware UTC. IDs are bigint. Tenant status: onboarding|backfilling|indexing|active|paused|error|archived.
- Tag slugs are stable across taxonomy rebuilds; manual edits (`is_pinned`, merges, aliases) always win on rebuild.
- Text normalization for matching: `kanalchi.text.normalize.normalize()` (NFKC, Cyrillic→Latin, diacritics stripped).
