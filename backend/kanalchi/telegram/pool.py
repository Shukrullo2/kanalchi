"""Telethon client pool supervisor (Phase 1 fills this in). For now it only publishes a heartbeat."""

from __future__ import annotations

import asyncio

from kanalchi.core.logging import get_logger
from kanalchi.core.redis import get_redis

log = get_logger(__name__)


class TelethonPool:
    async def run(self) -> None:
        log.info("telethon.pool.start")
        while True:
            try:
                await get_redis().set("hb:worker-telegram", "1", ex=120)
            except Exception as exc:  # noqa: BLE001
                log.warning("telethon.pool.heartbeat_failed", error=str(exc))
            await asyncio.sleep(30)
