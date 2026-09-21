# pg_dump from the official Postgres image + the MinIO client copied from its image (no runtime downloads).
FROM quay.io/minio/mc:latest AS mc
FROM postgres:17-alpine
COPY --from=mc /usr/bin/mc /usr/local/bin/mc
COPY backup.sh backup-loop.sh /
RUN chmod +x /backup.sh /backup-loop.sh
ENTRYPOINT ["/bin/sh", "/backup-loop.sh"]
