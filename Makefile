.DEFAULT_GOAL := help
COMPOSE_DEV := docker compose -f infra/compose.dev.yml
COMPOSE     := docker compose -f infra/compose.yml --env-file infra/.env

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------- local development (infra in Docker, api/web on the host) ----------
dev-infra: ## Start Postgres/Redis/MinIO/Caddy for local dev (ports 5433/6380/9002/8443)
	$(COMPOSE_DEV) up -d
dev-infra-down: ## Stop local infra
	$(COMPOSE_DEV) down
dev-infra-reset: ## Stop local infra and delete its volumes
	$(COMPOSE_DEV) down -v

setup: ## Install backend + web dependencies
	cd backend && uv sync
	cd web && npm install

migrate: ## Apply migrations + procrastinate schema (local)
	cd backend && uv run kanalchi migrate
migration: ## Autogenerate a migration: make migration m="add foo"
	cd backend && uv run alembic revision --autogenerate -m "$(m)"
seed: ## Create the demo tenant (demo.localhost)
	cd backend && uv run kanalchi seed-dev

api: ## Run the API with reload on :8001
	cd backend && uv run uvicorn kanalchi.api.main:app --reload --port 8001
worker-telegram: ## Run the telegram worker
	cd backend && uv run kanalchi worker telegram
worker-index: ## Run the index worker
	cd backend && uv run kanalchi worker index
worker-publish: ## Run the publish worker
	cd backend && uv run kanalchi worker publish
web: ## Run Next.js dev server on :3001
	cd web && npm run dev -- -p 3001

test: ## Backend tests
	cd backend && uv run pytest -q
lint: ## Lint backend + web
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd web && npm run lint
fmt: ## Format backend
	cd backend && uv run ruff format . && uv run ruff check --fix .

gen-keys: ## Print fresh APP_MASTER_KEY / SESSION_SECRET
	cd backend && uv run kanalchi gen-keys

# ---------- production (everything in Docker on the VPS) ----------
deploy: ## Build and (re)start the production stack
	$(COMPOSE) build
	$(COMPOSE) up -d migrate
	$(COMPOSE) up -d
logs: ## Tail production logs
	$(COMPOSE) logs -f --tail=200
ps: ## Production stack status
	$(COMPOSE) ps
backup-now: ## Run a backup immediately
	$(COMPOSE) exec backup sh /backup.sh
