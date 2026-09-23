#!/bin/sh
# Restore a dump from MinIO into the running postgres container.
# usage: infra/scripts/restore.sh kanalchi-20260921T030000Z.dump
set -eu
DUMP="$1"
cd "$(dirname "$0")/.."
# The compose file and its .env live here; the datastore credentials come from that file.
set -a
. ./.env
set +a
dc() { docker compose -f compose.yml "$@"; }
dc exec -T minio mc alias set local http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
dc exec -T minio mc cat "local/backups/postgres/$DUMP" > "/tmp/$DUMP"
dc stop api worker-telegram worker-index worker-publish
dc exec -T postgres dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"
dc exec -T postgres createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
dc exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner < "/tmp/$DUMP"
rm -f "/tmp/$DUMP"
dc start api worker-telegram worker-index worker-publish
echo "restore: done"
