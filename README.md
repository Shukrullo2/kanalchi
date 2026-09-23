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

Everything runs in Docker on one machine: Caddy (TLS), Next.js, FastAPI, three workers,
Postgres 17 + pgvector, Redis, MinIO and a nightly backup job. The stack is sized for an
**8 GB / 4 vCPU** droplet (Ubuntu 24.04); 4 GB is too small once a channel is being indexed.

### 1. DNS

| Record | Points to | Why |
|---|---|---|
| `admin.example.com` A | droplet IP | the admin panel (`ADMIN_HOST`) |
| `*.example.com` A | droplet IP | channels onboarded without a domain live at `<slug>.example.com` (`PLATFORM_DOMAIN`) |
| a blogger's own domain A | droplet IP | added later, per channel, and verified from the admin panel before a certificate is issued |

Use a DigitalOcean reserved IP if you can, so a rebuilt droplet keeps the address every
tenant's DNS points at. Certificates are issued automatically (Let's Encrypt): a normal one
for the admin host, on-demand ones for tenant domains after the API confirms the domain is
registered and its DNS resolves to `PUBLIC_IP`.

### 2. Telegram

- Create a **platform bot** with @BotFather. It signs admins in and sends alerts. Run
  `/setdomain` on it and give it `admin.example.com` (the Login Widget refuses other origins).
- Get `TG_API_ID` / `TG_API_HASH` from https://my.telegram.org for the Telethon reader accounts.
- Note your own numeric Telegram id (e.g. from @userinfobot) for `ADMIN_TG_IDS`.
- Each channel later gets its own bot from the onboarding wizard; the wizard prints the
  `/setdomain` value for it.

### 3. The droplet

```bash
ssh root@<droplet-ip>
curl -fsSL https://raw.githubusercontent.com/<you>/<repo>/main/infra/scripts/bootstrap-vps.sh | sh
git clone <repo> /opt/kanalchi && cd /opt/kanalchi
cp infra/.env.example infra/.env
```

The bootstrap installs Docker, adds a 4 GB swap file, turns on log rotation, unattended
security updates and fail2ban, and opens only SSH/80/443 in `ufw`. If you use DigitalOcean's
cloud firewall as well, allow the same three ports.

Fill in `infra/.env`. Every value under *App secrets*, *Telegram*, *AI providers* and
*Datastores* is required; `APP_ENV=prod` must stay set (it disables the dev login, requires
`APP_MASTER_KEY`, and marks cookies `Secure`). Generate the two secrets with:

```bash
docker run --rm -v "$PWD/backend:/app" -w /app ghcr.io/astral-sh/uv:python3.12-bookworm-slim uv run kanalchi gen-keys
```

or, if you have `uv` locally, `make gen-keys`. Then:

```bash
make deploy
make ps        # every service "running"/"healthy", migrate and minio-init "exited (0)"
make logs
```

`make deploy` builds the images, runs migrations, creates the MinIO buckets and starts
everything. The API refuses to start if `APP_ENV=prod` is combined with a missing master key
or the default session secret, so a half-filled `.env` fails loudly instead of running insecure.

### 4. First login and first channel

1. Open `https://admin.example.com`, sign in with the Telegram widget (your id must be in
   `ADMIN_TG_IDS`).
2. **Accounts** → add a Telegram reader account (phone, code, 2FA password). The session is
   stored Fernet-encrypted and only `worker-telegram` ever decrypts it.
3. **Onboard** → create the channel: link, reader account, optional own domain, optional bot
   token. The wizard shows a cost estimate before the import starts and a pipeline monitor after.
4. The blogger opens `https://<their-domain>/studio` and signs in with Telegram; they are let
   in if the channel's bot sees them as a channel admin, or if you invited them by Telegram id.

### 5. Updating

```bash
cd /opt/kanalchi && git pull && make deploy
```

Workers do not hot-reload; `make deploy` recreates every container whose image changed.
Old job signatures in the queue are the usual reason a worker fails right after a deploy; the
admin pipeline monitor flags jobs that never start.

### What each service costs in memory

Limits in `infra/compose.yml`: Postgres 2 GB, worker-telegram 1.2 GB, API and worker-index
768 MB each, Next.js and MinIO 512 MB each, Redis and worker-publish 256 MB, Caddy and backup
128 MB. Just under 7 GB in total, which is why the bootstrap adds swap on an 8 GB box.

## Operations

### Backups and restore

The `backup` service dumps Postgres nightly at 03:00 UTC into the MinIO `backups` bucket and keeps
14 days. Media lives in MinIO itself; mirror that bucket off-site as well if the channel content
matters to you (`mc mirror`).

Restore into a clean stack:

```bash
infra/scripts/restore.sh kanalchi-20260921T030000Z.dump
```

That stops the application containers, recreates the database, restores the dump and starts them
again. Practise it once before you need it: an untested backup is not a backup.

### What to watch

The platform bot messages every allow-listed admin when something needs a human, at most once an
hour per issue:

- a Telegram account has been signed out, which stops ingestion for its channels
- an extraction batch has been running for over 24 hours
- platform assistant spend has passed 80% of the daily cap
- `worker-telegram` has stopped reporting in

`/costs` on the admin domain shows spend by day, purpose, model and channel, all from measured
`usage` rather than estimates. Watch the cache hit rate there: if it drops below about 30%,
something volatile has crept into a cached prompt prefix and every call is paying full price.

### Cost control

Three independent limits, checked before any model call: a per-IP and per-visitor rate limit on
reader chat, a per-channel daily dollar budget, and a platform-wide daily cap. Bulk extraction goes
through the Message Batches API at half price, and the admin sees a measured cost estimate before a
batch is submitted.

## Repository layout

```
backend/   Python package `kanalchi`: core (settings, db, models), telegram (Telethon/aiogram), ai (Claude/Voyage),
           search, api (FastAPI), jobs (procrastinate), cli
web/       Next.js 16 app: proxy.ts (Host → tenant), app/t/[tenant] (viewer + studio), app/admin
infra/     compose.yml (prod), compose.dev.yml (local infra), Caddyfile(s), Postgres config, backup scripts
```
