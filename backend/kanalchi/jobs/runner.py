"""Worker entrypoint: `kanalchi worker <telegram|index|publish>`."""

from __future__ import annotations

import asyncio

from kanalchi.core.logging import configure_logging, get_logger
from kanalchi.jobs.app import app

log = get_logger(__name__)

# (queues, concurrency) per worker loop; the telegram process runs two loops so media downloads
# never starve the MTProto jobs and vice versa.
WORKER_LOOPS: dict[str, list[tuple[list[str], int]]] = {
    "telegram": [(["telegram"], 2), (["media"], 3)],
    "index": [(["index", "taxonomy"], 4)],
    "publish": [(["publish", "notify"], 2)],
}


async def run_worker(kind: str, concurrency: int | None = None) -> None:
    configure_logging()
    loops = WORKER_LOOPS[kind]
    log.info("worker.start", kind=kind, loops=[(q, concurrency or c) for q, c in loops])
    async with app.open_async():
        tasks: list[asyncio.Task] = []
        if kind == "telegram":
            from kanalchi.telegram.pool import TelethonPool

            tasks.append(asyncio.create_task(TelethonPool().run(), name="telethon-pool"))
        for i, (queues, conc) in enumerate(loops):
            tasks.append(
                asyncio.create_task(
                    app.run_worker_async(
                        queues=queues,
                        concurrency=concurrency or conc,
                        name=f"worker-{kind}-{i}",
                        install_signal_handlers=(i == 0),
                    ),
                    name=f"worker-{kind}-{i}",
                )
            )
        try:
            await asyncio.gather(*tasks)
        finally:
            for t in tasks:
                t.cancel()
