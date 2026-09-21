"""Pydantic schemas that drive structured outputs (extraction, taxonomy, discovery, voice).

`extra="forbid"` produces `additionalProperties: false`, which strict structured outputs require.
Keep every field required (use `| None` for optional values) and stay inside the JSON-Schema subset:
no `pattern`, no `minLength`, no `$ref` cycles.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EXTRACTOR_VERSION = 1
EXTRACT_PROMPT_VERSION = "x1"

Lang = Literal["uz-Latn", "uz-Cyrl", "ru", "en", "other"]
EntityType = Literal[
    "person", "gov_org", "org", "product", "location", "event", "law", "media_outlet", "tg_channel", "other"
]
PostFormat = Literal[
    "news",
    "announcement",
    "opinion",
    "analysis",
    "explainer",
    "ad",
    "poll",
    "repost",
    "quote",
    "personal",
    "qa",
    "giveaway",
    "event_invite",
    "meme",
    "other",
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Entity(Strict):
    type: EntityType
    surface: str = Field(description="exact wording as it appears in the post")
    normalized: str = Field(description="canonical full name in Latin script")
    lang: Lang
    role: Literal["subject", "mentioned", "quoted", "source"]
    sentiment_toward: Literal["positive", "neutral", "negative"] | None
    confidence: float


class ThemeCandidate(Strict):
    name: str = Field(description="1-4 words, Latin script, channel-agnostic wording")
    confidence: float


class DateRef(Strict):
    text: str
    iso: str | None
    precision: Literal["day", "month", "year", "range", "relative"]
    relation: Literal["past", "future", "ongoing", "unclear"]


class LinkAnnotation(Strict):
    url: str
    kind: Literal["news", "social", "official", "video", "shop", "telegram", "document", "other"]
    described_as: str | None


class Amount(Strict):
    value: str
    unit: str | None
    what: str


class CustomValue(Strict):
    dimension: str = Field(description="dimension key exactly as given in the dimension list")
    values: list[str]


class PostExtraction(Strict):
    """Everything extracted from one post in a single call."""

    language_primary: Literal["uz-Latn", "uz-Cyrl", "ru", "en", "mixed", "other"]
    language_secondary: list[Lang]
    format: PostFormat
    title: str = Field(description="<= 80 characters, in the language of the post")
    summary: str = Field(description="<= 280 characters, in the language of the post")
    themes: list[ThemeCandidate]
    entities: list[Entity]
    custom: list[CustomValue]
    links: list[LinkAnnotation]
    dates_referenced: list[DateRef]
    amounts: list[Amount]
    sentiment: Literal["positive", "neutral", "negative", "mixed"]
    stance_target: str | None
    stance: Literal["supportive", "critical", "neutral", "ambivalent"] | None
    key_claims: list[str]
    is_ad: bool
    advertiser: str | None
    has_call_to_action: bool
    is_low_content: bool
    hashtags: list[str]
    taxonomy_mapped: list[str] = Field(description="slugs from the provided taxonomy; empty on a cold start")
    new_candidates: list[str] = Field(description="names not present in the provided taxonomy")


# ----------------------------------------------------------------- discovery
class DiscoveredDimension(Strict):
    key: str = Field(description="snake_case, prefixed custom_, e.g. custom_dishes")
    label_uz: str
    label_ru: str
    label_en: str
    description: str
    extraction_hint: str = Field(
        description="one sentence telling the extractor what belongs in this dimension"
    )
    examples: list[str]


class ChannelProfile(Strict):
    title: str
    one_liner: str
    topics: list[str]
    audience: str
    formality: str = Field(description="tone and formality, e.g. 'formal news desk' or 'personal, playful'")
    language_mix: str
    posting_style: str
    custom_dimensions: list[DiscoveredDimension]


# ----------------------------------------------------------------- taxonomy
class TagProposal(Strict):
    canonical_name: str = Field(description="Latin script")
    label_uz: str
    label_ru: str
    label_en: str
    aliases: list[str] = Field(
        description="every script and language variant, including Cyrillic and Russian forms"
    )
    description: str = Field(description="<= 140 characters, English")
    parent_canonical: str | None
    merged_candidates: list[str] = Field(description="candidate names absorbed into this tag")
    keep_reason: Literal["frequent", "important_low_frequency"]


class TaxonomyProposal(Strict):
    dimension: str
    tags: list[TagProposal]
    dropped_candidates: list[str]
    notes: str


class TagMapping(Strict):
    candidate: str
    tag_canonical: str | None = Field(description="null when the candidate matches no existing tag")


class TagMappingBatch(Strict):
    mappings: list[TagMapping]


# ----------------------------------------------------------------- voice
class VoiceProfile(Strict):
    tone: str
    formality: str
    language_mix: str
    avg_length_chars: int
    sentence_style: str
    emoji_usage: str
    formatting_habits: list[str]
    openers: list[str]
    sign_offs: list[str]
    recurring_phrases: list[str]
    dos: list[str]
    donts: list[str]
    exemplar_excerpts: list[str]


def _inline(node: object, defs: dict) -> object:
    """Resolve every $ref against $defs so the schema has no indirection."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            target = defs[ref.split("/")[-1]]
            merged = {**_inline(target, defs), **{k: v for k, v in node.items() if k != "$ref"}}
            return merged
        return {k: _inline(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline(v, defs) for v in node]
    return node


def schema_of(model: type[BaseModel]) -> dict:
    """JSON schema for structured outputs: refs inlined, no $defs, additionalProperties false."""
    raw = model.model_json_schema()
    defs = raw.get("$defs", {})
    schema = _inline(raw, defs)
    assert isinstance(schema, dict)
    schema.pop("$defs", None)
    return schema
