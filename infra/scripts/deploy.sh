#!/usr/bin/env bash
# Server-side deploy, run by GitHub Actions over SSH (and by hand if needed).
#
#   deploy.sh [deploy] [<sha>]   fetch <sha> (default: origin/main), build on this host, restart
#   deploy.sh load <sha>         images arrive on stdin (gzipped `docker save`), nothing is built here
#
# The Actions key is installed with a forced command pointing here, so the arguments arrive in
# SSH_ORIGINAL_COMMAND and the key cannot run anything else. The repo is public, so the server
# fetches over HTTPS without credentials. infra/.env is untracked and never touched; it may set
# DEPLOY_COMPOSE (e.g. compose.reader.yml) to choose the stack.
#
# Everything lives in main(): bash has parsed the whole function before `git checkout`
# replaces this file on disk, so a deploy that changes the script itself is safe.
set -euo pipefail

main() {
  local root=/opt/kanalchi
  # shellcheck disable=SC2206
  local args=(${SSH_ORIGINAL_COMMAND:-$*})
  local mode=deploy want=""
  if [[ ${#args[@]} -gt 0 && ( "${args[0]}" == deploy || "${args[0]}" == load ) ]]; then
    mode="${args[0]}"; args=("${args[@]:1}")
  fi
  want="${args[0]:-}"
  if [[ -n "$want" && ! "$want" =~ ^[0-9a-f]{7,40}$ ]]; then
    echo "deploy: refusing argument '$want' (expected a commit sha)" >&2
    exit 2
  fi

  exec 9>/var/lock/kanalchi-deploy.lock
  flock -w 900 9 || { echo "deploy: another deploy is still running" >&2; exit 1; }

  cd "$root"
  if [[ "$mode" == load ]]; then
    echo "deploy: loading images from stdin"
    gunzip | docker load
  fi

  git fetch --quiet origin main
  local target
  target="$(git rev-parse origin/main)"
  if [[ -n "$want" ]]; then
    # Only ever deploy something that is on main.
    git merge-base --is-ancestor "$want" origin/main || { echo "deploy: $want is not on main" >&2; exit 2; }
    target="$(git rev-parse "$want")"
  fi
  echo "deploy: $(git rev-parse --short HEAD) -> $(git rev-parse --short "$target")"
  git checkout --quiet --force --detach "$target"

  local compose
  compose="$(sed -n 's/^DEPLOY_COMPOSE=//p' infra/.env | tail -1)"
  compose="${compose:-compose.yml}"
  local dc=(docker compose -f "infra/$compose" --env-file infra/.env)
  if [[ "$mode" == load ]]; then
    "${dc[@]}" up -d --no-build --remove-orphans
  else
    "${dc[@]}" build --pull
    "${dc[@]}" up -d --remove-orphans
  fi

  # Wait for the API to answer before calling the deploy good.
  local i
  for i in $(seq 1 60); do
    if [[ "$("${dc[@]}" ps api --format '{{.Health}}' 2>/dev/null)" == "healthy" ]]; then
      echo "deploy: api healthy on $(git rev-parse --short HEAD) ($compose)"
      docker image prune -f >/dev/null 2>&1 || true
      "${dc[@]}" ps --format 'table {{.Service}}\t{{.Status}}'
      return 0
    fi
    sleep 5
  done
  echo "deploy: api did not become healthy" >&2
  "${dc[@]}" ps
  "${dc[@]}" logs --tail=80 api migrate
  exit 1
}

main "$@"
