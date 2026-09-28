from datetime import UTC, datetime
from decimal import Decimal

from solders.pubkey import Pubkey

from mmkit.venue import manifest

# tests/fixtures/manifest_market.b64: a public SOL/USDC Manifest market at slot 451071501.
# Expected values from @cks-systems/manifest-sdk 0.2.38 parsing the same bytes.
SOL = Pubkey.from_string("So11111111111111111111111111111111111111112")
USDC = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
MAKER = Pubkey.from_string("DinRG9HNwgwVwtpaa2Ep3yGr69qqQHZGxkqB4hut7Kgg")


def test_header(market_bytes):
    m = manifest.parse(market_bytes)
    assert (m.base_mint, m.quote_mint, m.base_decimals, m.quote_decimals, m.size) == (SOL, USDC, 9, 6, 3936)


def test_book(market_bytes):
    m = manifest.parse(market_bytes)
    assert [(o.seq, o.base_atoms, o.price) for o in m.bids] == [(147, 999_999_999_999_995, Decimal("0.000001"))]
    assert [(o.seq, o.price) for o in m.asks] == [
        (149, Decimal(92)),
        (150, Decimal("269.999999")),
        (29, Decimal(270)),
        (151, Decimal("28694.269")),
        (152, Decimal("28694269.13")),
    ]
    assert m.asks[2].trader == Pubkey.from_string("9bRcrCQk5cnDPysYuwvAG2sT6Dpi1qqGhHDUU6c5KP4z")
    assert m.mine(MAKER, False) == [o for o in m.asks if o.seq != 29]


def test_seats(market_bytes):
    m = manifest.parse(market_bytes)
    assert len(m.seats) == 35
    assert m.seats[0] == manifest.Seat(Pubkey.from_string("U8JwPAUoK26JXsQk5mVDCd9X3coZmSxh9o71BCrxVxV"), 0, 0)
    assert m.seat(manifest.PROGRAM) is None


# tests/fixtures/fill_tx.json: a public SOL/USDC fill; expected values from the SDK's FillLog decoder.
SOL_USDC = Pubkey.from_string("ENhU8LsaR7vDD2G1CsWcsuSGNrih9Cv5WZEk7q9kPapQ")
FILL_MAKER = Pubkey.from_string("7GirX3rSwD283dshAkAptnNBb8bG4csWB5F1n6AybTiZ")
WHEN = datetime(2026, 9, 27, tzinfo=UTC)


def test_parse_fill(fill_tx):
    (f,) = manifest.parse_fills(fill_tx["logMessages"], 9, 6, fill_tx["signature"], WHEN)
    assert (f.market, f.maker) == (SOL_USDC, FILL_MAKER)
    assert str(f.taker) == "DB8EH6WQpdZxD7rQMHripx5mDV8ZSJv9aq2uRaei6rG1"
    assert (f.base_atoms, f.quote_atoms, f.maker_seq, f.taker_is_buy) == (105_568_539, 13_000_000, 88_460_915, True)
    assert round(f.price, 6) == Decimal("123.142747")


def test_ignores_other_logs():
    assert manifest.parse_fills(["Program log: hi", "Program data: AAAAAAAAAAA="], 6, 6, "sig", WHEN) == []


def test_ignores_fill_logs_from_other_programs(fill_tx):
    data = next(line for line in fill_tx["logMessages"] if line.startswith("Program data: "))
    forged = [
        "Program Evi1111111111111111111111111111111111111 invoke [1]",
        data,
        "Program Evi1111111111111111111111111111111111111 success",
    ]
    assert manifest.parse_fills(forged, 9, 6, "sig", WHEN) == []
    inside = [f"Program {manifest.PROGRAM} invoke [2]", data, f"Program {manifest.PROGRAM} success"]
    assert len(manifest.parse_fills(forged[:1] + inside + forged[2:], 9, 6, "sig", WHEN)) == 1
