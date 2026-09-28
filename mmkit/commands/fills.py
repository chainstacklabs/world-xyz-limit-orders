"""Fills over a period."""

from typing import Annotated

import typer

from mmkit import history
from mmkit.common import Json, emit, read_market, since
from mmkit.config import load, wallet

Period = Annotated[str, typer.Option(help="How far back: 30m, 24h, 7d")]
Everyone = Annotated[bool, typer.Option("--all", help="Every fill on the market, not just yours.")]


def main(period: Period = "24h", everyone: Everyone = False, as_json: Json = False) -> None:
    """Fills on your orders (or everyone's with --all), newest first."""
    cfg = load()
    read_market(cfg)  # refuses a wrong or missing venue.market before paging history
    me = None if everyone else wallet().pubkey()
    fs = [
        f
        for f in history.fills(cfg.market, since(period), cfg.base.decimals, cfg.quote.decimals)
        if me is None or f.maker == me
    ]
    side = lambda f: ("sold" if f.taker_is_buy else "bought") if me else ("buy" if f.taker_is_buy else "sell")
    rows = [
        {
            "time": f"{f.time:%Y-%m-%d %H:%M:%S} UTC",
            "side": side(f),
            "size": cfg.base.ui(f.base_atoms),
            "price": f.price,
            "value": cfg.quote.ui(f.quote_atoms),
            "tx": f.signature,
        }
        for f in fs
    ]
    emit(rows, as_json, f"fills, last {period}" + ("" if me else " — all traders; side is the taker's"))


if __name__ == "__main__":
    typer.run(main)
