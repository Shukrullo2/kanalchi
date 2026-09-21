"""Voyage embeddings: batching, rate limiting, token accounting and pgvector helpers."""

from __future__ import annotations

import asyncio
import time
from typing import Literal

import voyageai

from kanalchi.core.logging import get_logger
from kanalchi.core.pricing import embed_cost_usd
from kanalchi.core.settings import get_settings

log = get_logger(__name__)

BATCH = 128
# Only used when no token ceiling applies and an exact count would be wasted work.
# Measured at 1.83 on this archive's Uzbek Cyrillic, so this errs high on purpose.
CHARS_PER_TOKEN = 1.6
RATE_LIMIT_BACKOFF = 65.0
_client: voyageai.AsyncClient | None = None


def get_client() -> voyageai.AsyncClient:
    global _client
    if _client is None:
        s = get_settings()
        if not s.voyage_api_key:
            raise RuntimeError("VOYAGE_API_KEY is not configured")
        _client = voyageai.AsyncClient(api_key=s.voyage_api_key, max_retries=3)
    return _client


class _Pacer:
    """Spaces requests so a throttled account is not simply rejected.

    Voyage's free tier allows a few requests and a few thousand tokens a minute;
    exceeding either is an error rather than a queue, so the work has to be
    slowed down here instead. Both windows are enforced: a run of tiny requests
    hits the request ceiling, and one fat request hits the token ceiling.
    """

    def __init__(self, rpm: int, tpm: int) -> None:
        self.rpm = rpm
        self.tpm = tpm
        # Three requests a minute means one every twenty seconds, not three at
        # once and then a wait: the burst is what gets rejected.
        self.min_interval = 60.0 / rpm if rpm else 0.0
        self._sent: list[tuple[float, int]] = []  # (timestamp, tokens)
        self._last = 0.0
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self.rpm > 0 or self.tpm > 0

    async def wait(self, tokens: int) -> None:
        if not self.enabled:
            return
        async with self._lock:
            while True:
                now = time.monotonic()
                if self.min_interval and self._last:
                    gap = self.min_interval - (now - self._last)
                    if gap > 0:
                        await asyncio.sleep(gap)
                        now = time.monotonic()
                self._sent = [(t, n) for t, n in self._sent if now - t < 60]
                over_tokens = self.tpm and sum(n for _, n in self._sent) + tokens > self.tpm
                if not over_tokens:
                    self._sent.append((now, tokens))
                    self._last = now
                    return
                oldest = self._sent[0][0]
                delay = max(1.0, 60 - (now - oldest) + 1.0)
                log.debug("embed.paced", seconds=round(delay, 1), tokens=tokens)
                await asyncio.sleep(delay)


_pacer: _Pacer | None = None


def get_pacer() -> _Pacer:
    global _pacer
    if _pacer is None:
        s = get_settings()
        _pacer = _Pacer(s.embed_max_rpm, s.embed_max_tpm)
    return _pacer


def _token_counts(texts: list[str], model: str) -> list[int]:
    """Exact per-text token counts, or a deliberately high guess if that fails.

    Voyage's tokenizer runs locally, so this costs nothing but CPU — and against a
    hard per-minute ceiling a guess is not good enough: this archive's Uzbek
    Cyrillic is 1.83 characters per token, where a plausible-looking 2.2 put every
    request 20% over the line.
    """
    try:
        client = voyageai.Client(api_key=get_settings().voyage_api_key)
        return [client.count_tokens([t], model=model) for t in texts]
    except Exception as exc:  # noqa: BLE001
        log.warning("embed.tokenizer_unavailable", error=str(exc)[:200])
        return [max(1, int(len(t) / CHARS_PER_TOKEN)) for t in texts]


def _batches(texts: list[str], counts: list[int], max_tokens: int) -> list[list[int]]:
    """Group text indices into requests, splitting on the token ceiling when there is one."""
    if max_tokens <= 0:
        return [list(range(i, min(i + BATCH, len(texts)))) for i in range(0, len(texts), BATCH)]
    out: list[list[int]] = []
    current: list[int] = []
    budget = 0
    for i, cost in enumerate(counts):
        if current and (len(current) >= BATCH or budget + cost > max_tokens):
            out.append(current)
            current, budget = [], 0
        current.append(i)
        budget += cost
    if current:
        out.append(current)
    return out


async def _embed_with_backoff(client, payload: list[str], s, input_type: str, attempts: int):
    """A throttled account still says no occasionally; wait out the window rather than failing the job."""
    for attempt in range(attempts):
        try:
            return await client.embed(
                payload,
                model=s.embed_model,
                input_type=input_type,
                truncation=True,
                output_dimension=s.embed_dim,
            )
        except voyageai.error.RateLimitError:
            if attempt == attempts - 1:
                raise
            log.warning("embed.rate_limited", attempt=attempt + 1, sleeping=RATE_LIMIT_BACKOFF)
            await asyncio.sleep(RATE_LIMIT_BACKOFF)
    raise RuntimeError("unreachable")


async def embed(
    texts: list[str],
    *,
    input_type: Literal["document", "query"] = "document",
    tenant_id: int | None = None,
) -> tuple[list[list[float]], float]:
    """Embed texts in batches. Returns (vectors, cost_usd) and records the spend.

    Indexing the archive is throughput work and can be paced for hours. A reader's
    query is latency work and must never queue behind it, so queries skip the
    throttle entirely: if a rate-limited account refuses one, the caller drops the
    vector leg and answers from full text instead of making someone wait.
    """
    if not texts:
        return [], 0.0
    s = get_settings()
    client = get_client()
    interactive = input_type == "query"
    pacer = get_pacer()
    # Split the minute's token budget across the requests the minute allows, so
    # neither ceiling is left idle, with headroom because the token count here is
    # an estimate and going over is an error rather than a queue.
    per_request = 0
    if s.embed_max_tpm and not interactive:
        share = s.embed_max_tpm / s.embed_max_rpm if s.embed_max_rpm else s.embed_max_tpm
        per_request = max(512, int(share * 0.92))
    counts = _token_counts(texts, s.embed_model) if per_request else []
    groups = _batches(texts, counts, per_request)

    vectors: list[list[float]] = [[] for _ in texts]
    total_tokens = 0
    for group in groups:
        payload = [texts[i] for i in group]
        if not interactive:
            await pacer.wait(sum(counts[i] for i in group) if counts else 0)
        res = await _embed_with_backoff(client, payload, s, input_type, 1 if interactive else 4)
        for i, vector in zip(group, res.embeddings, strict=True):
            vectors[i] = vector
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
            requests=len(groups),
        )
    return vectors, usd


async def embed_one(
    text: str, *, input_type: Literal["document", "query"] = "query", tenant_id: int | None = None
) -> list[float]:
    vectors, _ = await embed([text], input_type=input_type, tenant_id=tenant_id)
    return vectors[0]
