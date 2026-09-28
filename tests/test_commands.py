from mmkit import cli

READ = ["markets", "market", "use", "verify", "wallet", "book", "orders", "fills", "stats", "probe", "simulate-fill"]
WRITE = ["swap", "split", "merge", "close", "create", "place", "amend", "cancel", "reprice", "withdraw", "exit"]


def test_all_commands_registered():
    assert sorted(c.name for c in cli.app.registered_commands) == sorted(READ + WRITE)


def test_every_write_command_takes_yes():
    from typer.testing import CliRunner

    for name in WRITE:
        out = CliRunner().invoke(cli.app, [name, "--help"], env={}).output
        assert "--send" in out and "--yes" in out, name


def test_yes_reaches_the_send(monkeypatch, tmp_path):
    import json
    from dataclasses import replace
    from decimal import Decimal

    from solders.keypair import Keypair
    from typer.testing import CliRunner

    from mmkit.commands import merge, place, reprice
    from mmkit.config import load
    from mmkit.venue import manifest

    from .conftest import FIXTURES, MARKET

    cfg = replace(load(FIXTURES / "market.json"), market=MARKET)
    me = Keypair()
    key = tmp_path / "k.json"
    key.write_text(json.dumps(list(bytes(me))))
    m = manifest.Market(
        cfg.base.mint,
        cfg.quote.mint,
        6,
        6,
        736,
        True,
        [],
        [manifest.Order(1, me.pubkey(), False, 1_000_000, Decimal("0.4"), 4 * 10**17)],
        [],
    )
    seen = []
    for mod in (merge, place, reprice):
        monkeypatch.setattr(mod, "load", lambda: cfg)
        monkeypatch.setattr(mod, "simulate_or_send", lambda *a, **k: seen.append(k.get("yes")))
        if hasattr(mod, "read_market"):
            monkeypatch.setattr(mod, "read_market", lambda c: m)
    monkeypatch.setattr(merge.rpc, "token_balance", lambda k: 5_000_000)
    for args in (["place", "ask", "1", "0.5"], ["reprice", "ask", "0.5"], ["merge", "1"]):
        r = CliRunner().invoke(cli.app, [*args, "--send", "--yes"], env={"WALLET_KEY": str(key)})
        assert r.exit_code == 0, (args, r.output)
    assert seen == [True, True, True]
