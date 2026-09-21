"""procrastinate application: Postgres-backed async job queue shared by api (deferring) and workers (running).

Queues:
  telegram  – everything that needs a Telethon client (login steps, resolve, backfill, resync, gap-fill)
  media     – media downloads (same worker process as `telegram`, separate concurrency)
  index     – embeddings, extraction batches, mapping, summaries, threads
  taxonomy  – long Opus taxonomy builds
  publish   – scheduled publishing via bots
  notify    – blogger DMs / platform alerts
"""

from __future__ import annotations

import procrastinate

from kanalchi.core.settings import get_settings

WORKER_QUEUES: dict[str, list[str]] = {
    "telegram": ["telegram", "media"],
    "index": ["index", "taxonomy"],
    "publish": ["publish", "notify"],
}


def _connector() -> procrastinate.PsycopgConnector:
    return procrastinate.PsycopgConnector(conninfo=get_settings().libpq_dsn)


app = procrastinate.App(
    connector=_connector(),
    import_paths=[
        "kanalchi.jobs.telegram_jobs",
        "kanalchi.jobs.index_jobs",
        "kanalchi.jobs.publish_jobs",
        "kanalchi.jobs.periodic",
    ],
)
