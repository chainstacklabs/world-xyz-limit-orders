from decimal import Decimal

import pytest

from mmkit.venue import manifest

from .conftest import MARKET, OWNER, PUBLIC_MARKET


def book(cfg, seat=(500_000, 40_000)):
    """Synthetic market: asks 1 @ 0.40 and 1.5 @ 0.42, bid 2 @ 0.30, and a seat with free balances."""
    o = lambda seq, bid, atoms, px: manifest.Order(seq, OWNER, bid, atoms, Decimal(px), int(Decimal(px) * 10**18))
    return manifest.Market(
        cfg.base.mint,
        cfg.quote.mint,
        6,
        6,
        736,
        True,
        bids=[o(3, True, 2_000_000, "0.30")],
        asks=[o(1, False, 1_000_000, "0.40"), o(2, False, 1_500_000, "0.42")],
        seats=[manifest.Seat(OWNER, *seat)] if seat else [],
    )


@pytest.mark.parametrize(
    ("price", "expected"),
    [
        ("0.35", (3_500_000_000, -10)),
        ("0.3", (3_000_000_000, -10)),
        ("0.5", (500_000_000, -9)),
        ("1", (1_000_000_000, -9)),
    ],
)
def test_price_encoding_matches_sdk(cfg, price, expected):
    p = manifest.order(False, 1, Decimal(price), cfg.base, cfg.quote)
    assert (p.mantissa, p.exponent) == expected


@pytest.mark.parametrize(("size", "price"), [(0, "0.3"), (1, "0"), (1, "-0.1")])
def test_order_rejects_nonpositive(cfg, size, price):
    with pytest.raises(SystemExit, match="must be positive"):
        manifest.order(True, size, Decimal(price), cfg.base, cfg.quote)


def test_bid_cost_rounds_up(cfg):
    assert manifest.order(True, 3, Decimal("0.35"), cfg.base, cfg.quote).quote_atoms() == 2


def test_batch_matches_sdk():
    # createBatchUpdateInstruction, @cks-systems/manifest-sdk 0.2.38; the program accepts this layout in simulation
    ix = manifest.batch(OWNER, MARKET, [7], [manifest.Place(False, 1_000_000, 3_500_000_000, -10)])
    assert bytes(ix.data).hex() == "0600010000000700000000000000000100000040420f000000000000c39dd0f6000000000000"
    assert [a.is_writable for a in ix.accounts] == [True, True, False]


def test_vault_matches_public_market_header(market_bytes):
    m = manifest.parse(market_bytes)
    assert bytes(manifest.vault(PUBLIC_MARKET, m.base_mint)) == market_bytes[80:112]
    assert bytes(manifest.vault(PUBLIC_MARKET, m.quote_mint)) == market_bytes[112:144]


def test_deposit_encoding(cfg):
    # program-side DepositParams { amount_atoms: u64, trader_index_hint: Option<u32> } — the SDK core builder adds a stray byte
    ix = manifest.deposit(OWNER, MARKET, cfg.base, 1_000_000)
    assert bytes(ix.data).hex() == "0240420f000000000000"
    assert ix.accounts[3].pubkey == manifest.vault(MARKET, cfg.base.mint)


def test_place_deposits_only_the_shortfall(cfg):
    ask = manifest.order(False, 2_000_000, Decimal("0.45"), cfg.base, cfg.quote)
    ixs = manifest.place_ixs(book(cfg), MARKET, OWNER, cfg.base, cfg.quote, ask)
    assert [bytes(i.data)[0] for i in ixs] == [2, 6, 5]
    assert bytes(ixs[0].data)[1:9] == (1_500_000).to_bytes(8, "little")  # 2 YES wanted, 0.5 free in seat


def test_place_claims_a_seat_first(cfg):
    ask = manifest.order(False, 2_000_000, Decimal("0.45"), cfg.base, cfg.quote)
    ixs = manifest.place_ixs(book(cfg, seat=None), MARKET, OWNER, cfg.base, cfg.quote, ask)
    assert [bytes(i.data)[0] for i in ixs] == [1, 2, 6, 5]


def test_reprice_bid_spends_only_free_quote(cfg):
    cancels, p = manifest.reprice(book(cfg), OWNER, cfg.base, cfg.quote, True, Decimal("0.20"))
    assert cancels == [3]
    assert p.base_atoms == 3_200_000  # (40_000 free + 600_000 locked) / 0.20
    assert p.quote_atoms() <= 640_000


def test_reprice_ask_moves_all_base(cfg):
    cancels, p = manifest.reprice(book(cfg), OWNER, cfg.base, cfg.quote, False, Decimal("0.50"))
    assert cancels == [1, 2]
    assert p.base_atoms == 3_000_000  # 2.5 resting + 0.5 free


def test_reprice_ixs_cancel_then_place(cfg):
    ixs = manifest.reprice_ixs(book(cfg), MARKET, OWNER, cfg.base, cfg.quote, False, Decimal("0.50"))
    assert [bytes(i.data)[0] for i in ixs] == [6, 5]


def test_reprice_nothing(cfg):
    with pytest.raises(SystemExit, match="nothing to reprice"):
        manifest.reprice(book(cfg), MARKET, cfg.base, cfg.quote, False, Decimal("0.50"))


def test_amend_price_up_deposits_the_difference(cfg):
    ixs = manifest.amend_ixs(book(cfg), MARKET, OWNER, cfg.base, cfg.quote, 3, None, Decimal("0.35"))
    assert [bytes(i.data)[0] for i in ixs] == [2, 6, 5]
    assert bytes(ixs[0].data)[1:9] == (60_000).to_bytes(8, "little")  # 2 @ 0.35 = 0.70; 0.60 freed + 0.04 free


def test_amend_size_down_needs_no_deposit(cfg):
    ixs = manifest.amend_ixs(book(cfg), MARKET, OWNER, cfg.base, cfg.quote, 1, 500_000, None)
    assert [bytes(i.data)[0] for i in ixs] == [6, 5]


def test_amend_unknown_order(cfg):
    with pytest.raises(SystemExit, match="no open order of yours with id 99"):
        manifest.amend_ixs(book(cfg), MARKET, OWNER, cfg.base, cfg.quote, 99, None, Decimal("0.3"))


def test_cancel_by_id(cfg):
    (ix,) = manifest.cancel_ixs(book(cfg), MARKET, OWNER, [1, 3])
    assert int.from_bytes(bytes(ix.data)[2:6], "little") == 2
    with pytest.raises(SystemExit, match="with id 7"):
        manifest.cancel_ixs(book(cfg), MARKET, OWNER, [1, 7])


def test_exit(cfg):
    m = book(cfg)
    (cancel,) = manifest.cancel_all_ixs(m, MARKET, OWNER)
    assert int.from_bytes(bytes(cancel.data)[2:6], "little") == 3
    wd = manifest.withdraw_all_ixs(m, MARKET, OWNER, cfg.base, cfg.quote)
    assert [bytes(i.data)[0] for i in wd] == [1, 3, 1, 3]  # create ATA, withdraw — per token
    assert manifest.cancel_all_ixs(m, MARKET, MARKET) == []
