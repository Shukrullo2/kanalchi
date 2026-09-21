#!/bin/sh
# Creates buckets and policies. Idempotent.
set -e
mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
for b in media uploads backups; do mc mb --ignore-existing "local/$b"; done
# Public read for post media (channel content is public anyway); uploads and backups stay private.
mc anonymous set download local/media
# Purge abandoned studio uploads after 7 days.
cat > /tmp/lifecycle.json <<'JSON'
{"Rules":[{"ID":"purge-tmp-uploads","Status":"Enabled","Filter":{"Prefix":""},"Expiration":{"Days":7}}]}
JSON
mc ilm import local/uploads < /tmp/lifecycle.json || true
echo "minio-init: done"
