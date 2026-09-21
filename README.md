# Kanalchi — AI helper for Telegram bloggers

Turns any Telegram channel into a web blog on its own domain: every post indexed, auto-tagged along
channel-specific dimensions (people, government bodies, links, themes, …), browsable by tag, and queryable
through an AI chat grounded in the full history. Three views:

- **Viewer** — followers browse posts by tag/entity/story and ask the channel questions (cited answers).
- **Blogger** (`/studio`) — idea board, research chat over their own posts, draft editor, scheduling, publish via the tenant bot.
- **Admin** (admin host) — onboard channels, manage Telegram accounts, watch jobs and spend.

Stack: FastAPI + Telethon + aiogram + procrastinate (Python 3.12) · Next.js 16 · Postgres 17 + pgvector · Redis · MinIO · Caddy.
AI: Claude Opus 5 (chat, taxonomy, drafting), Claude Sonnet 5 via Message Batches (bulk extraction), Voyage `voyage-4` embeddings.

The full design lives in the plan file used to build this repo; a condensed version is in `CLAUDE.md`.

## Local development

```bash
make setup          # uv sync + npm install
make dev-infra      # Postgres :5433, Redis :6380, MinIO :9002 (console :9003), Caddy https :8443
make migrate        # alembic + procrastinate schema
make seed           # creates tenant demo.localhost
make api            # FastAPI on :8001 (reload)
make web            # Next.js on :3001
make worker-telegram / worker-index / worker-publish
```

Open http://admin.localhost:8080 (admin) and http://demo.localhost:8080 (tenant); https is on :8443. Caddy uses an internal CA in dev;
accept the certificate warning once. Ports are offset so they never collide with other local projects.

Local config: copy `infra/.env.example` to `backend/.env` for the host processes (defaults already point at the dev
infra ports). Telegram login needs a real bot with `/setdomain`; in dev use `POST /api/auth/dev-login` instead.

## Production (single VPS, Docker Compose)

```bash
cp infra/.env.example infra/.env   # fill it in (make gen-keys for the secrets)
make deploy
```

Caddy issues certificates on demand for tenant domains that the admin has registered and DNS-verified.

## Repository layout

```
backend/   Python package `kanalchi`: core (settings, db, models), telegram (Telethon/aiogram), ai (Claude/Voyage),
           search, api (FastAPI), jobs (procrastinate), cli
web/       Next.js 16 app: proxy.ts (Host → tenant), app/t/[tenant] (viewer + studio), app/admin
infra/     compose.yml (prod), compose.dev.yml (local infra), Caddyfile(s), Postgres config, backup scripts
```
