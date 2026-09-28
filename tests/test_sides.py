import json

import pytest
from solders.pubkey import Pubkey
from typer.testing import CliRunner

from mmkit import cli, config, issuer, rpc, world
from mmkit.config import load
from mmkit.venue import manifest

from .conftest import FIXTURES, MARKET, OWNER, WORLD_MARKET
from .test_issuer import BASE_ACCOUNT, SPLIT_DATA, SPLIT_KEYS, SPLIT_OWNER

USDC = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")


def no_side(tmp_path):
    d = json.loads((FIXTURES / "market.json").read_text())
    d["base"], d["counterpart"] = d["counterpart"], d["base"]
    d["venue"]["side"] = "no"
    path = tmp_path / "no.json"
    path.write_text(json.dumps(d))
    return load(path)


# config


def test_yes_side_identities(cfg):
    assert (cfg.side, cfg.yes, cfg.no, cfg.collateral) == ("yes", cfg.base, cfg.counterpart, cfg.quote)


def test_no_side_identities(cfg, tmp_path):
    no = no_side(tmp_path)
    assert (no.side, no.base, no.counterpart) == ("no", cfg.counterpart, cfg.base)
    assert (no.yes, no.no) == (cfg.base, cfg.counterpart)


def test_collateral_separate_from_quote(tmp_path, cfg):
    d = json.loads((FIXTURES / "market.json").read_text())
    d["collateral"] = d["quote"]
    d["quote"] = {
        "symbol": "USDC",
        "mint": str(USDC),
        "decimals": 6,
        "tokenProgram": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    }
    path = tmp_path / "m.json"
    path.write_text(json.dumps(d))
    c = load(path)
    assert (c.quote.symbol, c.collateral.symbol) == ("USDC", "CASH")


# issuer: the same split from either side


def test_split_is_identical_from_the_no_side(cfg, tmp_path):
    for c in (cfg, no_side(tmp_path)):
        ix = issuer.split(c, SPLIT_OWNER, 12_771_627)
        keys = [str(a.pubkey) for a in ix.accounts]
        assert bytes(ix.data).hex() == SPLIT_DATA
        assert (
            keys[:BASE_ACCOUNT] + keys[BASE_ACCOUNT + 1 :] == SPLIT_KEYS[:BASE_ACCOUNT] + SPLIT_KEYS[BASE_ACCOUNT + 1 :]
        )


def test_split_uses_collateral_not_the_book_quote(cfg, tmp_path):
    d = json.loads((FIXTURES / "market.json").read_text())
    d["collateral"] = d["quote"]
    d["quote"] = {
        "symbol": "USDC",
        "mint": str(USDC),
        "decimals": 6,
        "tokenProgram": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    }
    path = tmp_path / "m.json"
    path.write_text(json.dumps(d))
    keys = [str(a.pubkey) for a in issuer.split(load(path), SPLIT_OWNER, 1).accounts]
    assert keys[2] == str(world.CASH) and str(USDC) not in keys


# world.to_config and use


def md_for(cfg):
    return {
        t.mint: {"symbol": t.symbol, "name": t.symbol, "uri": "", "decimals": t.decimals, "program": str(t.program)}
        for t in (cfg.base, cfg.quote, cfg.counterpart)
    }


def test_to_config_no_side(cfg, world_bytes, monkeypatch):
    monkeypatch.setattr(world, "metadata", lambda mints: md_for(cfg))
    d = world.to_config(world.parse_market(WORLD_MARKET, world_bytes), side="no")
    assert (d["base"]["symbol"], d["counterpart"]["symbol"], d["venue"]["side"]) == (
        cfg.counterpart.symbol,
        cfg.base.symbol,
        "no",
    )
    assert d["collateral"]["mint"] == str(world.CASH) and d["quote"]["mint"] == str(world.CASH)


def test_to_config_other_quote(cfg, world_bytes, monkeypatch):
    monkeypatch.setattr(world, "metadata", lambda mints: md_for(cfg))
    usdc = config.Token("USDC", USDC, 6, Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"))
    d = world.to_config(world.parse_market(WORLD_MARKET, world_bytes), quote=usdc)
    assert d["quote"]["symbol"] == "USDC" and d["collateral"]["symbol"] == "CASH"
    assert d["name"] == f"{cfg.base.symbol} / USDC"


def use(monkeypatch, world_bytes, cfg, existing, args):
    from mmkit.commands import use as cmd

    saved, looked = {}, []
    monkeypatch.setattr(rpc, "account", lambda key: rpc.Account(world_bytes, 1, Pubkey.default(), False))
    monkeypatch.setattr(world, "metadata", lambda mints: md_for(cfg))
    monkeypatch.setattr(cmd.manifest, "find_markets", lambda a, b: looked.append((a, b)) or [])
    monkeypatch.setattr(cmd.config, "save", lambda d: saved.update(d))
    monkeypatch.setattr(cmd.config, "existing", lambda: existing)
    r = CliRunner().invoke(cli.app, ["use", str(WORLD_MARKET), *args, "--json"], env={})
    return r, saved, looked


def test_use_no_side_looks_for_no_books(monkeypatch, world_bytes, cfg):
    r, saved, looked = use(monkeypatch, world_bytes, cfg, None, ["--side", "no"])
    assert r.exit_code == 0, r.output
    assert saved["venue"]["side"] == "no" and looked == [(cfg.counterpart.mint, world.CASH)]


def test_use_keeps_a_book_only_for_the_same_side(monkeypatch, world_bytes, cfg):
    old = {
        "name": "x",
        "issuer": {"ledger": str(WORLD_MARKET)},
        "venue": {"market": str(MARKET), "side": "yes"},
        "quote": {"mint": str(world.CASH)},
    }
    _, saved, _ = use(monkeypatch, world_bytes, cfg, old, [])
    assert saved["venue"]["market"] == str(MARKET)
    _, saved, _ = use(monkeypatch, world_bytes, cfg, old, ["--side", "no"])
    assert saved["venue"]["market"] is None


# withdraw


def seat_book(cfg, base=2_000_000, quote=500_000):
    return manifest.Market(cfg.base.mint, cfg.quote.mint, 6, 6, 736, True, [], [], [manifest.Seat(OWNER, base, quote)])


def test_withdraw_free_funds(cfg):
    ixs = manifest.withdraw_free_ixs(seat_book(cfg), MARKET, OWNER, cfg.quote, False, 300_000)
    assert [bytes(i.data)[0] for i in ixs] == [1, 3] and bytes(ixs[1].data)[1:9] == (300_000).to_bytes(8, "little")


def test_withdraw_all_free(cfg):
    ixs = manifest.withdraw_free_ixs(seat_book(cfg), MARKET, OWNER, cfg.base, True, None)
    assert bytes(ixs[1].data)[1:9] == (2_000_000).to_bytes(8, "little")


def test_withdraw_more_than_free_is_refused(cfg):
    with pytest.raises(SystemExit, match="only 0.5 CASH is free"):
        manifest.withdraw_free_ixs(seat_book(cfg), MARKET, OWNER, cfg.quote, False, 600_000)
    with pytest.raises(SystemExit, match="nothing free"):
        manifest.withdraw_free_ixs(seat_book(cfg, quote=0), MARKET, OWNER, cfg.quote, False, None)


def test_quote_token_from_its_mint(monkeypatch):
    from mmkit import books, spl

    mint = bytearray(82)
    mint[44] = 6
    monkeypatch.setattr(rpc, "account", lambda k: rpc.Account(bytes(mint), 1, spl.TOKEN_PROGRAM, False))
    t = books.token(str(USDC))
    assert (t.symbol, t.decimals, t.program) == ("USDC", 6, spl.TOKEN_PROGRAM)
    monkeypatch.setattr(rpc, "account", lambda k: None)
    with pytest.raises(SystemExit, match="not a token mint"):
        books.token(str(USDC))
