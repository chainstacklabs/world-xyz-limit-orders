import json
import subprocess
import sys
import urllib.error
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from solders.hash import Hash
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from typer.testing import CliRunner

from mmkit import cli, config, history, issuer, rpc, sim, spl, web
from mmkit.venue import manifest

from .conftest import FIXTURES, MARKET, OWNER, WORLD_MARKET

runner = CliRunner()


def order(seq, is_bid, atoms, price, trader=OWNER):
    return manifest.Order(seq, trader, is_bid, atoms, Decimal(price), int(Decimal(price) * 10**18))


# one-line errors


@pytest.mark.parametrize("fail", [ConnectionResetError("reset"), urllib.error.URLError("down")])
def test_rpc_network_errors_are_one_line(monkeypatch, fail):
    monkeypatch.setenv("RPC_URL", "http://127.0.0.1:1")

    def urlopen(*a, **k):
        raise fail

    monkeypatch.setattr(rpc.urllib.request, "urlopen", urlopen)
    with pytest.raises(SystemExit, match="RPC error — cannot reach RPC_URL"):
        rpc.call("getSlot", [])


def test_rpc_non_json_body_is_one_line(monkeypatch):
    monkeypatch.setenv("RPC_URL", "http://127.0.0.1:1")

    class Body:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"<html>bad gateway</html>"

    monkeypatch.setattr(rpc.urllib.request, "urlopen", lambda *a, **k: Body())
    with pytest.raises(SystemExit, match="RPC error — getSlot: not a JSON-RPC response"):
        rpc.call("getSlot", [])


def test_standalone_module_prints_one_line(tmp_path):
    key = tmp_path / "k.json"
    key.write_text(json.dumps(list(bytes(Keypair()))))
    env = {
        "RPC_URL": "http://127.0.0.1:1",
        "WALLET_KEY": str(key),
        "MARKET_FILE": str(FIXTURES / "market.json"),
        "PATH": "/usr/bin:/bin",
    }
    r = subprocess.run(
        [sys.executable, "-m", "mmkit.commands.wallet"], capture_output=True, text=True, env=env, check=False
    )
    assert r.returncode == 1 and "Traceback" not in r.stderr
    assert r.stderr.strip().startswith("RPC error — cannot reach RPC_URL") and len(r.stderr.strip().splitlines()) == 1


def test_web_network_error_is_one_line(monkeypatch):
    def urlopen(*a, **k):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(web.urllib.request, "urlopen", urlopen)
    with pytest.raises(SystemExit, match="https://example.com/x: unreachable"):
        web.get_json("https://example.com/x?secret=1")


@pytest.mark.parametrize("content", [None, "not json"])
def test_wallet_file_errors(tmp_path, monkeypatch, content):
    path = tmp_path / "k.json"
    if content:
        path.write_text(content)
    monkeypatch.setenv("WALLET_KEY", str(path))
    with pytest.raises(SystemExit, match="WALLET_KEY"):
        config.wallet()


def test_cancel_rejects_a_non_number():
    r = runner.invoke(cli.app, ["cancel", "abc"], env={})
    assert r.exit_code != 0 and "not an order id: abc" in r.output


def test_history_skips_missing_times_and_transactions(monkeypatch):
    sigs = [
        {"signature": "a", "blockTime": None, "err": None},
        {"signature": "b", "blockTime": 1_790_000_000, "err": None},
    ]
    monkeypatch.setattr(rpc, "call", lambda m, p: sigs if m == "getSignaturesForAddress" else None)
    assert history.fills(MARKET, datetime(2026, 1, 1, tzinfo=UTC), 6, 6) == []


# prices and amends


def test_rounding_never_beats_the_limit(cfg):
    price = Decimal("0.123456789012345")
    bid = manifest.order(True, 1, price, cfg.base, cfg.quote)
    ask = manifest.order(False, 1, price, cfg.base, cfg.quote)
    assert (bid.mantissa, bid.exponent) == (1_234_567_890, -10)
    assert (ask.mantissa, ask.exponent) == (1_234_567_891, -10)


def test_price_below_the_programs_range(cfg):
    with pytest.raises(SystemExit, match="too small"):
        manifest.order(True, 1, Decimal("1E-19"), cfg.base, cfg.quote)


def book(cfg, asks=(), bids=(), seat=(0, 0)):
    return manifest.Market(
        cfg.base.mint, cfg.quote.mint, 6, 6, 736, True, list(bids), list(asks), [manifest.Seat(OWNER, *seat)]
    )


@pytest.mark.parametrize(("size", "price"), [(0, None), (None, Decimal(0))])
def test_amend_zero_is_refused(cfg, size, price):
    m = book(cfg, asks=[order(1, False, 1_000_000, "0.4")])
    with pytest.raises(SystemExit, match="must be positive"):
        manifest.amend_ixs(m, MARKET, OWNER, cfg.base, cfg.quote, 1, size, price)


def test_crossing(cfg):
    stranger = Pubkey.default()
    m = book(cfg, asks=[order(1, False, 1, "0.40", stranger)], bids=[order(2, True, 1, "0.30", stranger)])
    assert manifest.crosses(m, True, Decimal("0.40")) and not manifest.crosses(m, True, Decimal("0.39"))
    assert manifest.crosses(m, False, Decimal("0.30")) and not manifest.crosses(m, False, Decimal("0.31"))
    assert not manifest.crosses(book(cfg), True, Decimal("0.99"))


def test_locked_quote_is_exact():
    o = manifest.Order(1, OWNER, True, 10**15, Decimal("0.3"), 3 * 10**17 + 1)
    assert o.locked_quote() == 300_000_000_000_000
    assert o.locked_quote(round_up=True) == 300_000_000_000_001


def test_parse_keeps_raw_price(market_bytes):
    (bid,) = manifest.parse(market_bytes).bids
    assert bid.price_d18 == 10**9  # 0.000001 USDC per SOL = 1e-9 quote atoms per base atom


def test_expiry_matches_the_program(market_bytes):
    data = bytearray(market_bytes)
    ask_root = int.from_bytes(data[164:168], "little")
    payload = manifest.HEADER + ask_root + manifest.NODE
    data[payload + 36 : payload + 40] = (100).to_bytes(
        4, "little"
    )  # last_valid_slot: after price 16, atoms 8, seq 8, trader 4
    seq = int.from_bytes(data[payload + 24 : payload + 32], "little")
    assert seq in {o.seq for o in manifest.parse(bytes(data), slot=100).asks}
    assert seq not in {o.seq for o in manifest.parse(bytes(data), slot=101).asks}


# rent and token accounts


def test_simulation_reports_rent_of_watched_accounts(monkeypatch, capsys):
    seen = []

    def call(method, params):
        seen.append(params[1])
        return {
            "value": {
                "err": None,
                "unitsConsumed": 1,
                "logs": [],
                "accounts": [{"lamports": 1_500_000_000}, {"lamports": 500_000_000}],
            }
        }

    monkeypatch.setenv("RPC_URL", "https://rpc.example.com")
    monkeypatch.setattr(rpc, "call", call)
    monkeypatch.setattr(rpc, "blockhash", Hash.default)
    kp = Keypair()
    ix = spl.create_ata(kp.pubkey(), config.Token("X", Pubkey.default(), 6, spl.TOKEN_2022_PROGRAM))
    sim.simulate_or_send([ix], kp, send=False, rent_of=(MARKET, OWNER))
    assert seen[0]["accounts"] == {"encoding": "base64", "addresses": [str(MARKET), str(OWNER)]}
    assert "rent locked for good: 2 SOL" in capsys.readouterr().out


def test_close_account_instruction(cfg):
    ix = spl.close_account(OWNER, cfg.base)
    assert bytes(ix.data) == bytes([9]) and ix.program_id == cfg.base.program
    assert [(a.pubkey, a.is_signer, a.is_writable) for a in ix.accounts] == [
        (spl.ata(OWNER, cfg.base), False, True),
        (OWNER, False, True),
        (OWNER, True, False),
    ]


@pytest.mark.parametrize(("yes", "no", "closed"), [(5, 5, 2), (5, 9, 1), (9, 9, 0)])
def test_merge_closes_the_accounts_it_empties(cfg, yes, no, closed):
    ixs = issuer.merge_ixs(cfg, OWNER, 5, yes, no)
    assert bytes(ixs[0].data)[:8] == bytes.fromhex("948dec2fae7e456f")
    assert len(ixs) == 1 + closed and all(bytes(i.data) == bytes([9]) for i in ixs[1:])


def test_close_only_empty_accounts(cfg):
    ixs = spl.close_empty(OWNER, [(cfg.base, 0), (cfg.counterpart, 3), (cfg.quote, None)])
    assert len(ixs) == 1 and ixs[0].accounts[0].pubkey == spl.ata(OWNER, cfg.base)


# use


def use_setup(monkeypatch, world_bytes, existing):
    from mmkit.commands import use

    saved = {}
    monkeypatch.setattr(rpc, "account", lambda key: rpc.Account(world_bytes, 1, Pubkey.default(), False))
    monkeypatch.setattr(
        use.world,
        "to_config",
        lambda m, side="yes", quote=None: {
            "name": "X / CASH",
            "base": {"mint": str(Pubkey.default())},
            "quote": {"mint": str(Pubkey.default())},
            "issuer": {"ledger": str(WORLD_MARKET)},
            "venue": {"market": None, "side": side},
        },
    )
    monkeypatch.setattr(use.manifest, "find_markets", lambda a, b: [])
    monkeypatch.setattr(use.config, "save", lambda d: saved.update(d))
    monkeypatch.setattr(use.config, "existing", lambda: existing)
    return saved


def test_use_refuses_to_replace_another_market(monkeypatch, world_bytes):
    use_setup(monkeypatch, world_bytes, {"name": "Other", "issuer": {"ledger": str(MARKET)}, "venue": {"market": None}})
    r = runner.invoke(cli.app, ["use", str(WORLD_MARKET)], env={})
    assert r.exit_code != 0 and "--force" in r.output


def test_use_keeps_a_created_market(monkeypatch, world_bytes):
    saved = use_setup(
        monkeypatch,
        world_bytes,
        {
            "name": "X / CASH",
            "issuer": {"ledger": str(WORLD_MARKET)},
            "venue": {"market": str(MARKET)},
            "quote": {"mint": str(Pubkey.default())},
        },
    )
    r = runner.invoke(cli.app, ["use", str(WORLD_MARKET), "--json"], env={})
    assert r.exit_code == 0 and saved["venue"]["market"] == str(MARKET)


# display


def test_split_validates_before_printing():
    r = runner.invoke(cli.app, ["split", "1.0000001"], env={"MARKET_FILE": str(FIXTURES / "market.json")})
    assert r.exit_code != 0 and "->" not in r.output and "not a valid" in r.output


def test_fill_times_say_utc(monkeypatch, cfg):
    from mmkit.commands import fills

    f = manifest.Fill(
        "sig", datetime(2026, 9, 28, 1, 2, 3, tzinfo=UTC), MARKET, OWNER, OWNER, 1, 1, Decimal("0.5"), 1, True
    )
    monkeypatch.setattr(fills, "load", lambda: replace(cfg, market=MARKET))
    monkeypatch.setattr(fills, "read_market", lambda c: None)
    monkeypatch.setattr(fills.history, "fills", lambda *a: [f])
    r = runner.invoke(cli.app, ["fills", "--all", "--json"], env={})
    assert json.loads(r.stdout)[0]["time"] == "2026-09-28 01:02:03 UTC"


def test_place_warns_when_it_crosses(monkeypatch, cfg, tmp_path):
    from mmkit.commands import place

    key = tmp_path / "k.json"
    key.write_text(json.dumps(list(bytes(Keypair()))))
    m = book(cfg, asks=[order(1, False, 1_000_000, "0.40", Pubkey.default())])
    monkeypatch.setattr(place, "load", lambda: replace(cfg, market=MARKET))
    monkeypatch.setattr(place, "read_market", lambda c: m)
    monkeypatch.setattr(place, "simulate_or_send", lambda *a, **k: None)
    r = runner.invoke(cli.app, ["place", "bid", "1", "0.45"], env={"WALLET_KEY": str(key)})
    assert "warning: 0.45 crosses the book (best ask 0.4)" in r.output
    r = runner.invoke(cli.app, ["place", "bid", "1", "0.35"], env={"WALLET_KEY": str(key)})
    assert "warning" not in r.output


def test_web_returns_a_json_error_body(monkeypatch):
    import io

    def urlopen(*a, **k):
        raise urllib.error.HTTPError(
            "https://x", 400, "Bad Request", {}, io.BytesIO(b'{"errorCode": "NO_ROUTES_FOUND"}')
        )

    monkeypatch.setattr(web.urllib.request, "urlopen", urlopen)
    assert web.get_json("https://x/quote") == {"errorCode": "NO_ROUTES_FOUND"}


def test_web_non_json_error_still_exits(monkeypatch):
    import io

    def urlopen(*a, **k):
        raise urllib.error.HTTPError("https://x", 502, "Bad Gateway", {}, io.BytesIO(b"<html>"))

    monkeypatch.setattr(web.urllib.request, "urlopen", urlopen)
    with pytest.raises(SystemExit, match="HTTP 502"):
        web.get_json("https://x/quote")
