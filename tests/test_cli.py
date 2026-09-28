import json
from dataclasses import replace
from decimal import Decimal

import pytest
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from typer.testing import CliRunner

from mmkit import cli, common, rpc
from mmkit.venue import manifest

from .conftest import PUBLIC_MARKET

runner = CliRunner()
COMMANDS = [c.name for c in cli.app.registered_commands]


def test_every_command_has_help():
    for name in COMMANDS:
        r = runner.invoke(cli.app, [name, "--help"], env={})
        assert r.exit_code == 0, (name, r.output)


def test_read_market_rejects_other_accounts(monkeypatch, cfg):
    monkeypatch.setattr(rpc, "account", lambda key: rpc.Account(b"", 1, Pubkey.default(), False))
    with pytest.raises(SystemExit, match="is not a Manifest market"):
        common.read_market(replace(cfg, market=PUBLIC_MARKET))


def test_read_market_rejects_another_pair(monkeypatch, cfg, market_bytes):
    monkeypatch.setattr(rpc, "account", lambda key: rpc.Account(market_bytes, 1, manifest.PROGRAM, False))
    monkeypatch.setattr(rpc, "slot", lambda: 1)
    with pytest.raises(SystemExit, match="for another pair"):
        common.read_market(replace(cfg, market=PUBLIC_MARKET))


def test_swap_validates_the_amount():
    r = runner.invoke(cli.app, ["swap", "cash", "sol", "1.0000005"], env={})
    assert r.exit_code != 0 and "not a valid CASH amount" in r.output


def test_verify_json(monkeypatch, cfg):
    from mmkit.commands import verify

    monkeypatch.setattr(verify, "load", lambda: cfg)
    monkeypatch.setattr(rpc, "account", lambda key: None)
    r = runner.invoke(cli.app, ["verify", "--json"], env={})
    rows, _ = json.JSONDecoder().raw_decode(
        r.stdout
    )  # CliRunner appends the SystemExit text to stdout; a real run puts it on stderr
    assert r.exit_code == 1 and {row["check"] for row in rows} >= {"issuer program", "world market"}
    assert all(row["ok"] == "FAIL" for row in rows)


def test_use_json(monkeypatch, tmp_path, world_bytes):
    from mmkit.commands import use

    from .conftest import WORLD_MARKET

    saved = {}
    monkeypatch.setattr(rpc, "account", lambda key: rpc.Account(world_bytes, 1, Pubkey.default(), False))
    monkeypatch.setattr(
        use.world,
        "to_config",
        lambda m, side="yes", quote=None: {
            "name": "X / CASH",
            "base": {"mint": str(Pubkey.default())},
            "quote": {"mint": str(Pubkey.default())},
            "venue": {"market": None, "side": side},
        },
    )
    monkeypatch.setattr(use.manifest, "find_markets", lambda a, b: [PUBLIC_MARKET])
    monkeypatch.setattr(use.config, "save", lambda d: saved.update(d))
    monkeypatch.setattr(use.config, "existing", lambda: None)
    r = runner.invoke(cli.app, ["use", str(WORLD_MARKET), "--json"], env={})
    assert json.loads(r.stdout) == {
        "name": "X / CASH",
        "side": "yes",
        "manifest_market": str(PUBLIC_MARKET),
        "manifest_markets": [str(PUBLIC_MARKET)],
    }
    assert saved["venue"]["market"] == str(PUBLIC_MARKET)


def test_text_formats_decimals():
    assert [common.text(v) for v in (Decimal("28694.269000"), Decimal("6E-9"), None, 7)] == [
        "28694.269",
        "0.000000006",
        "",
        "7",
    ]


def test_emit_one(capsys):
    common.emit_one({"price": Decimal("0.50"), "note": None}, False, "t")
    out = capsys.readouterr().out
    assert "0.5" in out and "0.50" not in out
    common.emit_one({"price": Decimal("0.50"), "note": None}, True)
    assert json.loads(capsys.readouterr().out) == {"price": "0.5", "note": None}


def test_since():
    with pytest.raises(Exception, match="30m, 24h, 7d"):
        common.since("yesterday")


def test_book_json_is_machine_readable(monkeypatch, cfg, tmp_path):
    from mmkit.commands import book

    me = Keypair()
    key = tmp_path / "k.json"
    key.write_text(json.dumps(list(bytes(me))))
    m = manifest.Market(cfg.base.mint, cfg.quote.mint, 6, 6, 736, True, [], [], [])
    m = replace(
        m,
        asks=[manifest.Order(1, me.pubkey(), False, 2_500_000, Decimal("0.4"), 4 * 10**17)],
        bids=[manifest.Order(2, Pubkey.default(), True, 1_000_000, Decimal("0.3"), 3 * 10**17)],
    )
    monkeypatch.setattr(book, "load", lambda: replace(cfg, market=PUBLIC_MARKET))
    monkeypatch.setattr(book, "read_market", lambda c: m)
    r = runner.invoke(cli.app, ["book", "--json"], env={"WALLET_KEY": str(key)})
    assert json.loads(r.output) == [
        {"side": "ask", "size": "2.5", "price": "0.4", "id": 1, "yours": True},
        {"side": "bid", "size": "1", "price": "0.3", "id": 2, "yours": False},
    ]


def test_checks_are_a_library_function(monkeypatch, cfg):
    from mmkit import checks

    monkeypatch.setattr(rpc, "account", lambda key: None)
    result = checks.run(cfg)
    assert "issuer program" in result and "world market" in result and not any(result.values())
