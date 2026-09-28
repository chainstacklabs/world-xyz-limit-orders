import base64
import json
from decimal import Decimal

import pytest
from solders.pubkey import Pubkey

from mmkit import routes, rpc, spl, taker
from mmkit.config import Token
from mmkit.venue import manifest

from .conftest import FIXTURES, MARKET, OWNER

# 1. swap builder


def test_swap_exact_in(cfg):
    ix = manifest.swap(OWNER, MARKET, cfg.base, cfg.quote, 2_000_000, 1_900_000, True)
    assert (
        bytes(ix.data).hex()
        == "04" + (2_000_000).to_bytes(8, "little").hex() + (1_900_000).to_bytes(8, "little").hex() + "0101"
    )
    assert [(a.pubkey, a.is_signer, a.is_writable) for a in ix.accounts] == [
        (OWNER, True, True),
        (MARKET, False, True),
        (spl.SYSTEM_PROGRAM, False, False),
        (spl.ata(OWNER, cfg.base), False, True),
        (spl.ata(OWNER, cfg.quote), False, True),
        (manifest.vault(MARKET, cfg.base.mint), False, True),
        (manifest.vault(MARKET, cfg.quote.mint), False, True),
        (cfg.base.program, False, False),
        (cfg.base.mint, False, False),
        (cfg.quote.mint, False, False),
    ]


def test_swap_quote_on_another_token_program(cfg):
    usdc = Token("USDC", Pubkey.default(), 6, spl.TOKEN_PROGRAM)
    keys = [a.pubkey for a in manifest.swap(OWNER, MARKET, cfg.base, usdc, 1, 0, False).accounts]
    assert keys[-3:] == [cfg.base.mint, spl.TOKEN_PROGRAM, usdc.mint]
    assert bytes(manifest.swap(OWNER, MARKET, cfg.base, usdc, 1, 0, False).data)[-2:] == bytes([0, 1])


# 2. routes


def test_world_route_legs():
    r = routes.parse("world", "buy", json.loads((FIXTURES / "world_order.json").read_text()))
    assert [(leg.venue, str(leg.key)) for leg in r.legs] == [
        ("DFlow Prediction Market Router", "DF1ow4tspfHX9JwWJsAb9epbkA8hmpSEAtxXy1V27QBH")
    ]
    assert (r.in_atoms, r.out_atoms, r.error) == (1_000_000, 3_234_758, None)
    assert not r.yours(MARKET)
    assert r.yours(Pubkey.from_string("DF1ow4tspfHX9JwWJsAb9epbkA8hmpSEAtxXy1V27QBH"))


def test_jupiter_route_legs():
    r = routes.parse("jupiter", "control", json.loads((FIXTURES / "jupiter_quote.json").read_text()))
    assert [leg.venue for leg in r.legs] == ["Meteora DLMM", "AlphaQ"]
    assert (r.in_atoms, r.out_atoms) == (10_000_000, 1_187_440)


def test_no_route_is_a_result_not_an_exception():
    r = routes.parse("jupiter", "buy", {"error": "No routes found", "errorCode": "NO_ROUTES_FOUND"})
    assert r.legs == [] and r.error == "NO_ROUTES_FOUND" and not r.yours(MARKET)


def test_unreachable_router_is_a_result(monkeypatch):
    def down(url, headers=None):
        raise SystemExit("unreachable or not JSON")

    monkeypatch.setattr(routes, "get_json", down)
    assert routes.world(Pubkey.default(), Pubkey.default(), 1).error == "unreachable or not JSON"


# 3. taker


def test_find_taker_skips_programs_and_empty_wallets(monkeypatch):
    rich, program, broke = Pubkey.new_unique(), Pubkey.new_unique(), Pubkey.new_unique()
    ta = [Pubkey.new_unique() for _ in range(3)]

    def call(method, params):
        if method == "getTokenLargestAccounts":
            return {"value": [{"address": str(a), "amount": "900"} for a in ta]}
        if method == "getMultipleAccounts" and params[0] == [str(a) for a in ta]:
            return {"value": [{"data": {"parsed": {"info": {"owner": str(o)}}}} for o in (program, broke, rich)]}
        return {
            "value": [
                {"owner": "BPFLoaderUpgradeab1e11111111111111111111111", "lamports": 10**10},
                {"owner": str(spl.SYSTEM_PROGRAM), "lamports": 1000},
                {"owner": str(spl.SYSTEM_PROGRAM), "lamports": 10**9},
            ]
        }

    monkeypatch.setattr(rpc, "call", call)
    assert taker.find_taker(Pubkey.default(), 500) == rich


def book(cfg, asks):
    return manifest.Market(cfg.base.mint, cfg.quote.mint, 6, 6, 736, True, [], asks, [])


def test_simulate_fill_reads_deltas(monkeypatch, cfg):
    t = Pubkey.new_unique()
    ask = manifest.Order(1, OWNER, False, 2_000_000, Decimal("0.4"), 4 * 10**17)
    seen = {}

    def token(amount):
        return {
            "data": [base64.b64encode(bytes(64) + amount.to_bytes(8, "little")).decode(), "base64"],
            "lamports": 1,
            "space": 165,
        }

    def call(method, params):
        seen["opts"] = params[1]
        return {
            "value": {
                "err": None,
                "logs": [],
                "unitsConsumed": 9,
                "accounts": [
                    token(2_000_000),
                    token(9_200_000),  # taker base after, taker quote after
                    {"data": ["", "base64"], "lamports": 5_000_000, "space": 736},
                ],
            }
        }

    monkeypatch.setattr(rpc, "call", call)
    monkeypatch.setattr(rpc, "token_balance", lambda k: 0 if k == spl.ata(t, cfg.base) else 10_000_000)
    monkeypatch.setattr(rpc, "account", lambda k: rpc.Account(bytes(736), 5_000_000, manifest.PROGRAM, False))
    f = taker.simulate_fill(book(cfg, [ask]), MARKET, cfg.base, cfg.quote, False, 2_000_000, t)
    assert seen["opts"]["sigVerify"] is False and seen["opts"]["replaceRecentBlockhash"] is True
    assert seen["opts"]["accounts"]["addresses"] == [str(spl.ata(t, cfg.base)), str(spl.ata(t, cfg.quote)), str(MARKET)]
    assert (f.spent, f.received, f.avg_price, f.market_grew, f.error) == (
        800_000,
        2_000_000,
        Decimal("0.4"),
        False,
        None,
    )


def test_average_price_is_readable():
    assert taker.PRICE.create_decimal(Decimal("269.9999190000242999927100022")) == Decimal("269.9999190")


def test_simulate_fill_reports_growth_and_errors(monkeypatch, cfg):
    t = Pubkey.new_unique()
    ask = manifest.Order(1, OWNER, False, 1_000_000, Decimal("0.4"), 4 * 10**17)
    monkeypatch.setattr(rpc, "token_balance", lambda k: 10_000_000)
    monkeypatch.setattr(rpc, "account", lambda k: rpc.Account(bytes(736), 5_000_000, manifest.PROGRAM, False))
    monkeypatch.setattr(
        rpc,
        "call",
        lambda m, p: {
            "value": {
                "err": {"InstructionError": [1, "Custom"]},
                "logs": ["a", "Program log: no fill"],
                "accounts": None,
            }
        },
    )
    f = taker.simulate_fill(book(cfg, [ask]), MARKET, cfg.base, cfg.quote, False, 1_000_000, t)
    assert f.error.startswith("{'InstructionError'") and "no fill" in f.logs[-1]


def test_simulate_fill_needs_your_side(cfg):
    with pytest.raises(SystemExit, match="no asks to fill"):
        taker.simulate_fill(book(cfg, []), MARKET, cfg.base, cfg.quote, False, 1, Pubkey.default())


# 4. commands


def test_commands_are_read_only_and_hyphenated():
    from mmkit import cli

    names = {c.name for c in cli.app.registered_commands}
    assert {"probe", "simulate-fill"} <= names
    assert {m.__name__.rsplit(".", 1)[1] for m in cli.READ} >= {"probe", "simulate_fill"}


def test_probe_json(monkeypatch, cfg):
    from typer.testing import CliRunner

    from mmkit import cli
    from mmkit.commands import probe

    seen = []

    def quote(router):
        def q(a, b, atoms, side=""):
            seen.append((router, side))
            return routes.Route(router, side, [routes.Leg("Manifest", MARKET)], atoms, atoms * 3)

        return q

    monkeypatch.setattr(probe, "load", lambda: __import__("dataclasses").replace(cfg, market=MARKET))
    monkeypatch.setattr(probe.routes, "world", quote("world"))
    monkeypatch.setattr(probe.routes, "jupiter", quote("jupiter"))
    r = CliRunner().invoke(cli.app, ["probe", "--size", "2", "--json"], env={})
    rows = json.loads(r.stdout)
    assert [(row["router"], row["side"]) for row in rows] == [
        ("world", "buy"),
        ("world", "sell"),
        ("jupiter", "buy"),
        ("jupiter", "sell"),
        ("jupiter", "control"),
    ]
    assert rows[0]["yours"] is True and rows[0]["venues"] == "Manifest" and rows[0]["price"] == "0.3333"
    assert rows[0]["gets"] == "6 BTC-UP" and rows[1]["gets"] == "6 CASH"  # 2 in, 3x out
    assert rows[1]["price"] == "3"


def test_find_taker_when_the_rpc_refuses_the_search(monkeypatch):
    def call(method, params):
        raise rpc.RpcError("getTokenLargestAccounts: Too many accounts requested")

    monkeypatch.setattr(rpc, "call", call)
    with pytest.raises(SystemExit, match="can't list the largest holders .* pass --taker"):
        taker.find_taker(Pubkey.default(), 1)


def test_probe_rows_are_a_library_function(monkeypatch, cfg):
    from dataclasses import replace

    monkeypatch.setattr(
        routes,
        "world",
        lambda a, b, atoms, side="": routes.Route("world", side, [routes.Leg("Manifest", MARKET)], atoms, atoms * 2),
    )
    monkeypatch.setattr(
        routes, "jupiter", lambda a, b, atoms, side="": routes.Route("jupiter", side, error="NO_ROUTES_FOUND")
    )
    rows = routes.probe(replace(cfg, market=MARKET), Decimal(1))
    assert [(r["router"], r["side"], r["yours"], r["price"]) for r in rows][:2] == [
        ("world", "buy", True, Decimal("0.5000")),
        ("world", "sell", True, Decimal("2.0000")),
    ]
    assert rows[-1]["side"] == "control" and rows[-1]["error"] == "NO_ROUTES_FOUND"
