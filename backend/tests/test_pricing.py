from kanalchi.core.pricing import Usage, cost_usd, embed_cost_usd


def test_opus_cost_with_cache():
    u = Usage(input_tokens=1000, output_tokens=500, cache_write_tokens=2000, cache_read_tokens=10000)
    usd = cost_usd("claude-opus-5", u)
    expected = (1000 * 5 + 500 * 25 + 2000 * 6.25 + 10000 * 0.5) / 1e6
    assert abs(usd - expected) < 1e-9


def test_batch_halves_price():
    u = Usage(input_tokens=1_000_000)
    assert cost_usd("claude-sonnet-5", u, batch=True) == 1.0


def test_unknown_model_never_undercounts():
    assert cost_usd("claude-mystery", Usage(input_tokens=1_000_000)) == 5.0


def test_usage_from_response_object():
    class U:
        input_tokens = 10
        output_tokens = 20
        cache_creation_input_tokens = 30
        cache_read_input_tokens = 40

    u = Usage.from_response(U())
    assert u.as_dict() == {
        "input_tokens": 10,
        "output_tokens": 20,
        "cache_write_tokens": 30,
        "cache_read_tokens": 40,
    }


def test_embed_cost():
    assert embed_cost_usd("voyage-4", 1_000_000) == 0.12
