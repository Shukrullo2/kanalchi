"""USD pricing tables and usage → cost helpers. Prices are per million tokens (Anthropic first-party API)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# input, output, cache_write (5m), cache_write (1h), cache_read  — all $/MTok
_MODEL_PRICES: dict[str, tuple[float, float, float, float, float]] = {
    "claude-opus-5": (5.00, 25.00, 6.25, 10.00, 0.50),
    "claude-sonnet-5": (2.00, 10.00, 2.50, 4.00, 0.20),
    "claude-haiku-4-5": (1.00, 5.00, 1.25, 2.00, 0.10),
    "claude-fable-5-1": (10.00, 50.00, 12.50, 20.00, 0.25),
}
_EMBED_PRICES: dict[str, float] = {  # $/MTok
    "voyage-4": 0.12,
    "voyage-4-lite": 0.06,
    "voyage-4-large": 0.18,
}


@dataclass(slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0

    @classmethod
    def from_response(cls, usage: Any) -> Usage:
        """Build from an anthropic `Message.usage` (object or dict)."""
        get = (lambda k: getattr(usage, k, None)) if not isinstance(usage, dict) else usage.get
        return cls(
            input_tokens=int(get("input_tokens") or 0),
            output_tokens=int(get("output_tokens") or 0),
            cache_write_tokens=int(get("cache_creation_input_tokens") or 0),
            cache_read_tokens=int(get("cache_read_input_tokens") or 0),
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cache_read_tokens": self.cache_read_tokens,
        }


def cost_usd(model: str, usage: Usage, *, batch: bool = False, cache_ttl_1h: bool = False) -> float:
    base = model.split("@")[0]
    prices = _MODEL_PRICES.get(base)
    if prices is None:
        # Unknown model: assume Opus-tier so we never under-count spend.
        prices = _MODEL_PRICES["claude-opus-5"]
    inp, out, cw5, cw1h, cr = prices
    cw = cw1h if cache_ttl_1h else cw5
    usd = (
        usage.input_tokens * inp
        + usage.output_tokens * out
        + usage.cache_write_tokens * cw
        + usage.cache_read_tokens * cr
    ) / 1_000_000
    return usd * (0.5 if batch else 1.0)


def embed_cost_usd(model: str, tokens: int) -> float:
    return tokens * _EMBED_PRICES.get(model, 0.12) / 1_000_000
