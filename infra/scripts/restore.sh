#!/bin/sh
# Restore a dump from MinIO into the running postgres container.
# usage: infra/scripts/restore.sh kanalchi-20260921T030000Z.dump
set -eu
DUMP="$1"
cd "$(dirname "$0")/.."
docker compose exec -T minio mc alias set local http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
docker compose exec -T minio mc cat "local/backups/postgres/$DUMP" > "/tmp/$DUMP"
docker compose stop api worker-telegram worker-index worker-publish
docker compose exec -T postgres dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"
docker compose exec -T postgres createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
docker compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner < "/tmp/$DUMP"
docker compose start api worker-telegram worker-index worker-publish
echo "restore: done"
