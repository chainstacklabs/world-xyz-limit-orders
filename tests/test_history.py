from datetime import UTC, datetime
from decimal import Decimal

from solders.pubkey import Pubkey

from mmkit import history, rpc
from mmkit.venue import manifest

SOL_USDC = Pubkey.from_string("ENhU8LsaR7vDD2G1CsWcsuSGNrih9Cv5WZEk7q9kPapQ")
MAKER = Pubkey.from_string("7GirX3rSwD283dshAkAptnNBb8bG4csWB5F1n6AybTiZ")
WHEN = datetime(2026, 9, 27, tzinfo=UTC)


def fill(maker, taker_is_buy, base, quote):
    return manifest.Fill("s", WHEN, SOL_USDC, maker, MAKER, base, quote, Decimal(0), 1, taker_is_buy)


def test_stats_for_a_maker():
    me, other = Pubkey.default(), MAKER
    fs = [fill(me, True, 2_000_000, 1_000_000), fill(me, False, 4_000_000, 1_200_000), fill(other, True, 9, 9)]
    s = history.stats(fs, 6, 6, me)
    assert (s.fills, s.volume, s.notional, s.bought, s.sold) == (2, 6_000_000, 2_200_000, 4_000_000, 2_000_000)
    assert (s.avg_buy, s.avg_sell) == (Decimal("0.3"), Decimal("0.5"))
    assert history.stats(fs, 6, 6).fills == 3
    assert history.stats([], 6, 6).avg_buy is None


def test_fills_stops_at_since(monkeypatch, fill_tx):
    sigs = [
        {"signature": "new", "blockTime": 1_790_536_243, "err": None},
        {"signature": "old", "blockTime": 1_700_000_000, "err": None},
    ]
    calls = []

    def call(method, params):
        calls.append(method)
        return sigs if method == "getSignaturesForAddress" else {"meta": {"logMessages": fill_tx["logMessages"]}}

    monkeypatch.setattr(rpc, "call", call)
    fs = history.fills(SOL_USDC, datetime(2026, 1, 1, tzinfo=UTC), 9, 6)
    assert [f.signature for f in fs] == ["new"]
    assert calls == ["getSignaturesForAddress", "getTransaction"]
