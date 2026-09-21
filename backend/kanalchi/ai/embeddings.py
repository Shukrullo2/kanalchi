"""Voyage embeddings: batching, token accounting and pgvector helpers."""

from __future__ import annotations

from typing import Literal

import voyageai

from kanalchi.core.logging import get_logger
from kanalchi.core.pricing import embed_cost_usd
from kanalchi.core.settings import get_settings

log = get_logger(__name__)

BATCH = 128
_client: voyageai.AsyncClient | None = None


def get_client() -> voyageai.AsyncClient:
    global _client
    if _client is None:
        s = get_settings()
        if not s.voyage_api_key:
            raise RuntimeError("VOYAGE_API_KEY is not configured")
        _client = voyageai.AsyncClient(api_key=s.voyage_api_key, max_retries=3)
    return _client


async def embed(
    texts: list[str],
    *,
    input_type: Literal["document", "query"] = "document",
    tenant_id: int | None = None,
) -> tuple[list[list[float]], float]:
    """Embed texts in batches. Returns (vectors, cost_usd) and records the spend."""
    if not texts:
        return [], 0.0
    s = get_settings()
    client = get_client()
    vectors: list[list[float]] = []
    total_tokens = 0
    for i in range(0, len(texts), BATCH):
        chunk = texts[i : i + BATCH]
        res = await client.embed(
            chunk, model=s.embed_model, input_type=input_type, truncation=True, output_dimension=s.embed_dim
        )
        vectors.extend(res.embeddings)
        total_tokens += getattr(res, "total_tokens", 0) or 0
    usd = embed_cost_usd(s.embed_model, total_tokens)
    if tenant_id is not None and total_tokens:
        from kanalchi.ai.claude import record_usage
        from kanalchi.core.pricing import Usage

        await record_usage(
            tenant_id,
            s.embed_model,
            "embed",
            Usage(input_tokens=total_tokens),
            provider="voyage",
            cost=usd,
            requests=len(range(0, len(texts), BATCH)),
        )
    return vectors, usd


async def embed_one(
    text: str, *, input_type: Literal["document", "query"] = "query", tenant_id: int | None = None
) -> list[float]:
    vectors, _ = await embed([text], input_type=input_type, tenant_id=tenant_id)
    return vectors[0]
