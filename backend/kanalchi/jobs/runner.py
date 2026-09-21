"""Worker entrypoint: `kanalchi worker <telegram|index|publish>`."""

from __future__ import annotations

import asyncio

from kanalchi.core.logging import configure_logging, get_logger
from kanalchi.jobs.app import WORKER_QUEUES, app

log = get_logger(__name__)


async def run_worker(kind: str, concurrency: int | None = None) -> None:
    configure_logging()
    queues = WORKER_QUEUES[kind]
    conc = concurrency or {"telegram": 4, "index": 4, "publish": 2}[kind]
    log.info("worker.start", kind=kind, queues=queues, concurrency=conc)
    async with app.open_async():
        supervisors = []
        if kind == "telegram":
            from kanalchi.telegram.pool import TelethonPool

            pool = TelethonPool()
            supervisors.append(asyncio.create_task(pool.run(), name="telethon-pool"))
        try:
            await app.run_worker_async(
                queues=queues,
                concurrency=conc,
                name=f"worker-{kind}",
                install_signal_handlers=True,
            )
        finally:
            for t in supervisors:
                t.cancel()
