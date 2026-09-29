#!/usr/bin/env bash
# Visits on the production sites, from Caddy's access log on the droplet.
#   tools/visits.sh "2026-09-29T10:50:00Z"          # since a moment (UTC or with offset)
#   tools/visits.sh "2h"                            # or a docker-style duration
set -euo pipefail
since="${1:-1h}"
host="${DROPLET:-root@161.35.79.4}"
ssh -o BatchMode=yes -o ConnectTimeout=10 "$host" \
  "cd /opt/kanalchi && docker compose -f infra/compose.yml --env-file infra/.env logs --since '$since' --no-log-prefix caddy 2>/dev/null | grep '\"request\"'" \
| python3 "$(dirname "$0")/visits.py" "$since"
