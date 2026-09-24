"""Telethon client pool: the single owner of every MTProto session.

Runs inside worker-telegram. Jobs on the `telegram`/`media` queues obtain a client with `get_pool().client(account_id)`
and serialize MTProto traffic per account with `get_pool().lock(account_id)`. Live channel updates are handled here too.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from telethon import TelegramClient, events, utils
from telethon.errors import (
    AuthKeyUnregisteredError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
    SessionRevokedError,
    UserDeactivatedBanError,
)
from telethon.sessions import StringSession
from telethon.tl.types import PeerChannel

from kanalchi.core.crypto import decrypt, encrypt
from kanalchi.core.db import session_scope
from kanalchi.core.logging import get_logger
from kanalchi.core.models import Channel, TelegramAccount, Tenant
from kanalchi.core.redis import get_redis
from kanalchi.core.settings import get_settings

log = get_logger(__name__)

REFRESH_S = 30
LOGIN_TTL_S = 600


class PoolError(RuntimeError):
    pass


@dataclass(slots=True)
class PendingLogin:
    client: TelegramClient
    phone: str
    phone_code_hash: str
    expires_at: float


@dataclass(slots=True)
class LiveChannel:
    channel_id: int
    tenant_id: int
    tg_channel_id: int
    access_hash: int | None


@dataclass
class AccountRuntime:
    account_id: int
    client: TelegramClient
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    channels: dict[int, LiveChannel] = field(default_factory=dict)  # marked peer id → channel
    handlers: list[Any] = field(default_factory=list)


_POOL: TelethonPool | None = None


def get_pool() -> TelethonPool:
    if _POOL is None:
        raise PoolError(
            "Telethon pool is not running in this process (jobs on the telegram queue must run in worker-telegram)"
        )
    return _POOL


def _new_client(session: str | None) -> TelegramClient:
    s = get_settings()
    if not s.tg_api_id or not s.tg_api_hash:
        raise PoolError("TG_API_ID / TG_API_HASH are not configured")
    return TelegramClient(
        StringSession(session),
        s.tg_api_id,
        s.tg_api_hash,
        device_model="Kanalchi",
        system_version="Linux",
        app_version="1.0",
        lang_code="en",
        system_lang_code="en",
        flood_sleep_threshold=60,
        catch_up=True,
    )


class TelethonPool:
    def __init__(self) -> None:
        global _POOL
        self.accounts: dict[int, AccountRuntime] = {}
        self.pending: dict[int, PendingLogin] = {}
        _POOL = self

    # ------------------------------------------------------------------ lifecycle
    async def run(self) -> None:
        log.info("telethon.pool.start")
        while True:
            try:
                await self.refresh()
                await get_redis().set("hb:worker-telegram", str(int(time.time())), ex=120)
            except Exception as exc:  # noqa: BLE001
                log.exception("telethon.pool.refresh_failed", error=str(exc))
            self._expire_pending()
            await asyncio.sleep(REFRESH_S)

    async def refresh(self) -> None:
        async with session_scope() as db:
            accounts = (
                await db.scalars(
                    select(TelegramAccount).where(TelegramAccount.status.in_(["active", "flood_wait"]))
                )
            ).all()
            channels = (
                await db.scalars(
                    select(Channel)
                    .join(Tenant, Tenant.id == Channel.tenant_id)
                    .where(
                        Channel.telegram_account_id.is_not(None),
                        # The archive plan is a snapshot: no live updates after the import.
                        or_(Tenant.plan.is_(None), Tenant.plan != "archive"),
                    )
                )
            ).all()
        wanted = {a.id: a for a in accounts}
        by_account: dict[int, dict[int, LiveChannel]] = {}
        for c in channels:
            marked = utils.get_peer_id(PeerChannel(c.tg_channel_id))
            by_account.setdefault(c.telegram_account_id, {})[marked] = LiveChannel(
                c.id, c.tenant_id, c.tg_channel_id, c.access_hash
            )

        for acc_id in list(self.accounts):
            if acc_id not in wanted:
                await self._stop(acc_id)
        for acc_id, acc in wanted.items():
            if acc_id not in self.accounts and acc.session_enc:
                await self._start(acc)
            rt = self.accounts.get(acc_id)
            if rt is not None:
                new = by_account.get(acc_id, {})
                if set(new) != set(rt.channels):
                    rt.channels = new
                    self._register_handlers(rt)
                    await self._enqueue_gap_fill(new.values())

    async def _start(self, acc: TelegramAccount) -> None:
        try:
            client = _new_client(decrypt(acc.session_enc or ""))
            await client.connect()
            if not await client.is_user_authorized():
                raise AuthKeyUnregisteredError(request=None)
            me = await client.get_me()
        except (AuthKeyUnregisteredError, SessionRevokedError, UserDeactivatedBanError) as exc:
            log.error("telethon.account.dead", account_id=acc.id, error=type(exc).__name__)
            await self._set_status(acc.id, "dead", last_error=type(exc).__name__)
            return
        except Exception as exc:  # noqa: BLE001
            log.exception("telethon.account.start_failed", account_id=acc.id, error=str(exc))
            return
        rt = AccountRuntime(account_id=acc.id, client=client)
        self.accounts[acc.id] = rt
        await self._set_status(acc.id, "active", tg_user_id=me.id, display_name=utils.get_display_name(me))
        log.info("telethon.account.started", account_id=acc.id, user=utils.get_display_name(me))

    async def _stop(self, acc_id: int) -> None:
        rt = self.accounts.pop(acc_id, None)
        if rt:
            try:
                await rt.client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            log.info("telethon.account.stopped", account_id=acc_id)

    async def _set_status(self, acc_id: int, status: str, **health: Any) -> None:
        async with session_scope() as db:
            acc = await db.get(TelegramAccount, acc_id)
            if acc is None:
                return
            acc.status = status
            acc.last_seen_at = datetime.now(UTC)
            if "tg_user_id" in health:
                acc.tg_user_id = health.pop("tg_user_id")
            if "display_name" in health:
                acc.display_name = health.pop("display_name")
            h = dict(acc.health or {})
            h.update({k: v for k, v in health.items()})
            h["last_ok_at" if status == "active" else "last_error_at"] = datetime.now(UTC).isoformat()
            acc.health = h

    # ------------------------------------------------------------------ access for jobs
    def client(self, account_id: int | None) -> TelegramClient:
        if account_id is None or account_id not in self.accounts:
            raise PoolError(f"account {account_id} is not connected in this worker")
        return self.accounts[account_id].client

    def lock(self, account_id: int) -> asyncio.Lock:
        return self.accounts[account_id].lock

    def input_peer(self, channel: Channel):  # noqa: ANN201
        from telethon.tl.types import InputPeerChannel

        if channel.access_hash is not None:
            return InputPeerChannel(channel.tg_channel_id, channel.access_hash)
        return PeerChannel(channel.tg_channel_id)

    # ------------------------------------------------------------------ live updates
    def _register_handlers(self, rt: AccountRuntime) -> None:
        for cb, _ in rt.handlers:
            rt.client.remove_event_handler(cb)
        rt.handlers.clear()
        chats = list(rt.channels)
        if not chats:
            return

        async def on_new(event: events.NewMessage.Event) -> None:
            await self._dispatch("new", rt, event.chat_id, event.message)

        async def on_edit(event: events.MessageEdited.Event) -> None:
            await self._dispatch("edit", rt, event.chat_id, event.message)

        async def on_delete(event: events.MessageDeleted.Event) -> None:
            if event.chat_id is None:
                return
            await self._dispatch("delete", rt, event.chat_id, list(event.deleted_ids))

        for cb, builder in (
            (on_new, events.NewMessage(chats=chats)),
            (on_edit, events.MessageEdited(chats=chats)),
            (on_delete, events.MessageDeleted(chats=chats)),
        ):
            rt.client.add_event_handler(cb, builder)
            rt.handlers.append((cb, builder))
        log.info("telethon.handlers.registered", account_id=rt.account_id, channels=len(chats))

    async def _dispatch(self, kind: str, rt: AccountRuntime, chat_id: int, payload: Any) -> None:
        live = rt.channels.get(chat_id)
        if live is None:
            return
        from kanalchi.telegram import ingest

        try:
            if kind == "delete":
                await ingest.mark_deleted(live.channel_id, payload)
            else:
                await ingest.ingest_live_message(live.channel_id, payload, edited=(kind == "edit"))
        except Exception as exc:  # noqa: BLE001
            log.exception("telethon.live.failed", kind=kind, channel_id=live.channel_id, error=str(exc))

    async def _enqueue_gap_fill(self, channels) -> None:  # noqa: ANN001
        from kanalchi.jobs import telegram_jobs

        for live in channels:
            try:
                await telegram_jobs.backfill_chunk.configure(
                    queueing_lock=f"backfill:{live.channel_id}"
                ).defer_async(channel_id=live.channel_id)
            except Exception as exc:  # noqa: BLE001
                if "already" not in str(exc).lower():
                    log.warning("telethon.gap_fill.defer_failed", channel_id=live.channel_id, error=str(exc))

    # ------------------------------------------------------------------ login handshake
    def _expire_pending(self) -> None:
        now = time.time()
        for acc_id, p in list(self.pending.items()):
            if p.expires_at < now:
                self.pending.pop(acc_id, None)
                asyncio.create_task(p.client.disconnect())  # type: ignore[arg-type]

    async def login_start(self, account_id: int) -> None:
        async with session_scope() as db:
            acc = await db.get(TelegramAccount, account_id)
            if acc is None:
                return
            phone = acc.phone
        old = self.pending.pop(account_id, None)
        if old:
            await old.client.disconnect()
        client = _new_client(None)
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
        except Exception as exc:  # noqa: BLE001
            await self._set_status(account_id, "pending_code", last_error=f"send_code failed: {exc}")
            await client.disconnect()
            raise
        self.pending[account_id] = PendingLogin(
            client, phone, sent.phone_code_hash, time.time() + LOGIN_TTL_S
        )
        await self._set_status(account_id, "pending_code", login_stage="code_sent", last_error=None)
        log.info("telethon.login.code_sent", account_id=account_id)

    async def login_code(self, account_id: int, code: str) -> None:
        p = self.pending.get(account_id)
        if p is None:
            await self._set_status(account_id, "pending_code", last_error="login expired; request a new code")
            return
        try:
            await p.client.sign_in(p.phone, code, phone_code_hash=p.phone_code_hash)
        except SessionPasswordNeededError:
            await self._set_status(
                account_id, "pending_password", login_stage="password_needed", last_error=None
            )
            return
        except (PhoneCodeInvalidError, PhoneCodeExpiredError) as exc:
            await self._set_status(account_id, "pending_code", last_error=type(exc).__name__)
            return
        await self._finish_login(account_id, p)

    async def login_password(self, account_id: int, password: str) -> None:
        p = self.pending.get(account_id)
        if p is None:
            await self._set_status(account_id, "pending_code", last_error="login expired; request a new code")
            return
        try:
            await p.client.sign_in(password=password)
        except Exception as exc:  # noqa: BLE001
            await self._set_status(
                account_id, "pending_password", last_error=f"password rejected: {type(exc).__name__}"
            )
            return
        await self._finish_login(account_id, p)

    async def _finish_login(self, account_id: int, p: PendingLogin) -> None:
        self.pending.pop(account_id, None)
        me = await p.client.get_me()
        session_str = p.client.session.save()
        async with session_scope() as db:
            acc = await db.get(TelegramAccount, account_id)
            if acc is None:
                return
            acc.session_enc = encrypt(session_str)
            acc.tg_user_id = me.id
            acc.display_name = utils.get_display_name(me)
            acc.status = "active"
            acc.health = {
                **(acc.health or {}),
                "login_stage": "done",
                "last_error": None,
                "last_ok_at": datetime.now(UTC).isoformat(),
            }
        self.accounts[account_id] = AccountRuntime(account_id=account_id, client=p.client)
        log.info("telethon.login.done", account_id=account_id, user=utils.get_display_name(me))
