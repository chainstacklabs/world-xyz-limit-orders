"""One World market in detail."""

from decimal import Decimal

import typer
from solders.pubkey import Pubkey

from mmkit import books, rpc, world
from mmkit.common import Json, emit_one


def main(address: str, as_json: Json = False) -> None:
    """What a World market asks, when it trades, what it holds and what World's router prices it at."""
    key = Pubkey.from_string(address)
    acc = rpc.account(key)
    if acc is None:
        raise SystemExit(f"{address} not found — closed, or not a market address")
    m = world.parse_market(key, acc.data)
    md = world.metadata([m.yes_mint, m.no_mint])
    if m.yes_mint not in md:
        raise SystemExit(f"{address} is closed")
    idx, label = books.index(), {m.yes_mint: "YES", m.no_mint: "NO"}
    emit_one(
        {
            "market": address,
            "question": world.description(md[m.yes_mint]["uri"]),
            "yes": md[m.yes_mint]["symbol"],
            "no": md[m.no_mint]["symbol"],
            "window_start": m.start,
            "window_end": m.end,
            "status": m.status(),
            "cash_locked": Decimal(rpc.token_balance(m.vault)) / world.ONE,
            "yes_buy": world.buy_price(m, m.yes_mint),
            "yes_sell": world.sell_price(m, m.yes_mint),
            "no_buy": world.buy_price(m, m.no_mint),
            "no_sell": world.sell_price(m, m.no_mint),
            "books": [books.describe(b, label) for mint in (m.yes_mint, m.no_mint) for b in idx.get(mint, [])],
        },
        as_json,
        "World's prices: CASH per token. Books: public Manifest order books, prices in their own quote. No window: the question holds the deadline",
    )


if __name__ == "__main__":
    typer.run(main)
