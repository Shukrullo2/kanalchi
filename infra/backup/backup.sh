#!/bin/sh
# Nightly logical backup of Postgres into the MinIO "backups" bucket (14-day retention).
# Env: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, PGHOST, S3_ENDPOINT, MINIO_ROOT_USER, MINIO_ROOT_PASSWORD
set -eu
export PGPASSWORD="$POSTGRES_PASSWORD"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
FILE="/tmp/kanalchi-$STAMP.dump"
pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "$FILE"
mc alias set local "$S3_ENDPOINT" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc cp "$FILE" "local/backups/postgres/" >/dev/null
rm -f "$FILE"
mc rm --recursive --force --older-than 14d local/backups/postgres/ >/dev/null 2>&1 || true
echo "backup: uploaded kanalchi-$STAMP.dump"
