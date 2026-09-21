"""message_fields() and engagement() against hand-built Telethon message stand-ins."""

from datetime import UTC, datetime
from types import SimpleNamespace

from telethon.tl import types as tl

from kanalchi.telegram.ingest import engagement, group_by_album, message_fields


def make_msg(
    msg_id: int = 10,
    text: str = "",
    entities=None,
    grouped_id=None,
    views: int = 0,
    forwards: int = 0,
    reactions=None,
    media=None,
    file=None,
) -> tl.Message:
    m = tl.Message(id=msg_id, peer_id=tl.PeerChannel(1), message=text, date=datetime(2026, 1, 2, tzinfo=UTC))
    m.entities = entities or []
    m.grouped_id = grouped_id
    m.views = views
    m.forwards = forwards
    m.reactions = reactions
    m.media = media
    m.edit_date = None
    m.reply_to = None
    m.fwd_from = None
    object.__setattr__(m, "_file", file)
    return m


class FakeFile(SimpleNamespace):
    pass


def test_plain_text_message():
    f = message_fields(make_msg(text="Salom", views=100, forwards=3))
    assert f["tg_message_id"] == 10
    assert f["text"] == "Salom"
    assert f["text_norm"] == "salom"
    assert f["html"] == "Salom"
    assert f["media_kind"] == "none"
    assert f["views"] == 100 and f["forwards"] == 3
    assert f["content_hash"]


def test_service_message_is_skipped():
    assert message_fields(tl.MessageService(id=1, peer_id=tl.PeerChannel(1), date=datetime.now(UTC), action=None)) is None


def test_reactions_are_summed():
    reactions = tl.MessageReactions(
        results=[
            tl.ReactionCount(reaction=tl.ReactionEmoji("👍"), count=5),
            tl.ReactionCount(reaction=tl.ReactionCustomEmoji(123), count=2),
        ],
        min=False,
        can_see_list=False,
        reactions_as_tags=False,
    )
    f = message_fields(make_msg(reactions=reactions))
    assert f["reactions_total"] == 7
    assert {"emoji": "👍", "count": 5} in f["reactions"]
    assert {"custom_emoji_id": 123, "count": 2} in f["reactions"]


def test_cyrillic_text_norm_is_latin():
    f = message_fields(make_msg(text="Тошкент ҳокимлиги"))
    assert f["text_norm"] == "toshkent hokimligi"


def test_content_hash_changes_with_text_only():
    a = message_fields(make_msg(text="one", views=1))
    b = message_fields(make_msg(text="one", views=999))
    c = message_fields(make_msg(text="two", views=1))
    assert a["content_hash"] == b["content_hash"]  # counters must not trigger re-indexing
    assert a["content_hash"] != c["content_hash"]


def test_urls_extracted_into_field():
    text = "read gazeta.uz today"
    ents = [{"_": "MessageEntityUrl", "offset": 5, "length": 9}]
    f = message_fields(make_msg(text=text, entities=[tl.MessageEntityUrl(offset=5, length=9)]))
    assert f["_urls"] == ["https://gazeta.uz"]
    assert ents  # entity dicts are produced by Telethon's to_dict()


def test_engagement_weighting():
    assert engagement(views=1000, forwards=2, reactions_total=10) == 10 * 5 + 2 * 10 + 10


def test_group_by_album():
    msgs = [make_msg(1, grouped_id=7), make_msg(2, grouped_id=7), make_msg(3)]
    groups = group_by_album(msgs)
    assert [len(g) for g in groups] == [2, 1]
