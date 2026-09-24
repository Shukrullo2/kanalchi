"""Bot API checks: is a user an admin of the channel; does the bot have posting rights."""

from __future__ import annotations

from aiogram import Bot
from aiogram.types import ChatMemberAdministrator, ChatMemberOwner


def bot_chat_id(tg_channel_id: int) -> int:
    """Telethon exposes bare channel ids; the Bot API wants the -100 prefixed form."""
    return int(f"-100{tg_channel_id}") if tg_channel_id > 0 else tg_channel_id


def bare_channel_id(chat_id: int) -> int:
    """The reverse: a Bot API chat id (-100…) back to the bare id the channels table stores."""
    text = str(chat_id)
    return int(text[4:]) if text.startswith("-100") else abs(chat_id)


async def public_channel_info(bot_token: str, username: str) -> dict | None:
    """What the Bot API tells anyone about a public channel: id, title, description, member count.
    None when the username is not a channel the bot can see."""
    try:
        async with Bot(bot_token) as bot:
            chat = await bot.get_chat(f"@{username}")
            if chat.type != "channel":
                return None
            try:
                members = await bot.get_chat_member_count(chat.id)
            except Exception:  # noqa: BLE001
                members = None
    except Exception:  # noqa: BLE001
        return None
    return {
        "tg_channel_id": bare_channel_id(chat.id),
        "title": chat.title or "",
        "about": chat.description,
        "participants_count": members,
    }


async def is_channel_admin(bot_token: str, tg_channel_id: int, user_tg_id: int) -> bool:
    try:
        async with Bot(bot_token) as bot:
            admins = await bot.get_chat_administrators(bot_chat_id(tg_channel_id))
    except Exception:  # noqa: BLE001
        return False
    return any(a.user.id == user_tg_id for a in admins)


async def bot_can_post(bot_token: str, tg_channel_id: int) -> tuple[bool, str]:
    try:
        async with Bot(bot_token) as bot:
            me = await bot.get_me()
            member = await bot.get_chat_member(bot_chat_id(tg_channel_id), me.id)
    except Exception as exc:  # noqa: BLE001
        return False, f"bot api error: {exc}"
    if isinstance(member, ChatMemberOwner):
        return True, "owner"
    if isinstance(member, ChatMemberAdministrator) and member.can_post_messages:
        return True, "administrator"
    return False, f"bot is {member.status} without post rights"
