from decimal import Decimal

import pytest

from mmkit.config import load, require_market, rpc_url, save_market

from .conftest import FIXTURES, PUBLIC_MARKET


def test_load(cfg):
    assert cfg.base.symbol == "BTC-UP" and cfg.quote.decimals == 6
    assert cfg.market is None


def test_atoms_round_trip(cfg):
    assert cfg.quote.atoms("12.5") == 12_500_000
    assert cfg.quote.ui(12_500_000) == Decimal("12.5")


@pytest.mark.parametrize("bad", ["0.0000001", "-1", "NaN", "Infinity", "abc"])
def test_atoms_rejects_bad_amount(cfg, bad):
    with pytest.raises(SystemExit, match="not a valid CASH amount"):
        cfg.quote.atoms(bad)


def test_missing_file(tmp_path):
    with pytest.raises(SystemExit, match="mm use"):
        load(tmp_path / "market.json")


def test_empty_market_and_save(tmp_path, cfg):
    path = tmp_path / "market.json"
    path.write_text((FIXTURES / "market.json").read_text())
    with pytest.raises(SystemExit, match="mm create"):
        require_market(load(path))
    save_market(PUBLIC_MARKET, path)
    assert load(path).market == PUBLIC_MARKET


def test_rpc_url_required(monkeypatch):
    monkeypatch.delenv("RPC_URL", raising=False)
    with pytest.raises(SystemExit, match="RPC_URL is not set"):
        rpc_url()


def test_chosen_book():
    from mmkit.config import chosen_book

    new = {"issuer": {"ledger": "L"}, "venue": {"side": "yes"}, "quote": {"mint": "Q"}}
    old = {"issuer": {"ledger": "L"}, "venue": {"side": "yes", "market": "MINE"}, "quote": {"mint": "Q"}}
    assert chosen_book(old, new, ["OTHER"]) == "MINE"  # a book you set for the same market, side and quote stays
    assert chosen_book(None, new, ["ONLY"]) == "ONLY"
    assert chosen_book(None, new, ["A", "B"]) is None  # ambiguous: you choose
    assert chosen_book(old | {"venue": {"side": "no", "market": "MINE"}}, new, []) is None
