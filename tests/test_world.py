import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from solders.pubkey import Pubkey

from mmkit import world

from .conftest import FIXTURES, WORLD_MARKET


def test_parse_market(cfg, world_bytes):
    m = world.parse_market(WORLD_MARKET, world_bytes)
    assert (m.cash_mint, m.yes_mint, m.no_mint, m.vault) == (
        cfg.quote.mint,
        cfg.base.mint,
        cfg.counterpart.mint,
        cfg.issuer.collateral_vault,
    )
    assert (m.start, m.end) == (datetime(2026, 7, 21, 23, 10, tzinfo=UTC), datetime(2026, 7, 21, 23, 15, tzinfo=UTC))
    assert m.ended()


def test_long_dated_market_has_no_window(world_bytes):
    no_window = world_bytes[:258] + bytes(16) + world_bytes[274:]
    m = world.parse_market(WORLD_MARKET, no_window)
    assert m.end is None and not m.ended()


def test_rejects_other_accounts(world_bytes):
    with pytest.raises(SystemExit, match="not a World market"):
        world.parse_market(WORLD_MARKET, bytes(8) + world_bytes[8:])


def test_to_config_is_market_json(cfg, world_bytes, monkeypatch):
    m = world.parse_market(WORLD_MARKET, world_bytes)
    md = {
        t.mint: {"symbol": t.symbol, "name": t.symbol, "uri": "", "decimals": t.decimals, "program": str(t.program)}
        for t in (cfg.base, cfg.quote, cfg.counterpart)
    }
    monkeypatch.setattr(world, "metadata", lambda mints: md)
    assert world.to_config(m) == json.loads((FIXTURES / "market.json").read_text())


def test_closed_market(world_bytes, monkeypatch):
    monkeypatch.setattr(world, "metadata", lambda mints: {})
    with pytest.raises(SystemExit, match="closed"):
        world.to_config(world.parse_market(WORLD_MARKET, world_bytes))


def test_router_quote_no_route(monkeypatch):
    monkeypatch.setattr(world, "get_json", lambda url, headers: {"error": "no route"})
    assert world.router_quote(Pubkey.default(), Pubkey.default(), 1) is None


def test_router_quote_unreachable(monkeypatch):
    def down(url, headers):
        raise OSError("network down")

    monkeypatch.setattr(world, "get_json", down)
    assert world.router_quote(Pubkey.default(), Pubkey.default(), 1) is None


def test_world_prices_per_token(monkeypatch, world_bytes):
    m = world.parse_market(WORLD_MARKET, world_bytes)
    monkeypatch.setattr(world, "router_quote", lambda a, b, atoms: 3_000_000 if a == m.cash_mint else 400_000)
    assert world.buy_price(m, m.yes_mint) == Decimal("0.3333")  # 1 CASH buys 3 tokens
    assert world.sell_price(m, m.yes_mint) == Decimal("0.4")
    monkeypatch.setattr(world, "router_quote", lambda a, b, atoms: None)
    assert world.buy_price(m, m.yes_mint) is None and world.sell_price(m, m.yes_mint) is None
