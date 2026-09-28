"""What your fills add up to over a period."""

from typing import Annotated

import typer

from mmkit import history
from mmkit.common import Json, emit_one, read_market, since
from mmkit.config import load, wallet

Period = Annotated[str, typer.Option(help="How far back: 30m, 24h, 7d")]
Everyone = Annotated[bool, typer.Option("--all", help="The whole market, not just you.")]


def main(period: Period = "7d", everyone: Everyone = False, as_json: Json = False) -> None:
    """Fill count, volume, what you bought and sold, and at what average price."""
    cfg = load()
    read_market(cfg)  # refuses a wrong or missing venue.market before paging history
    me = None if everyone else wallet().pubkey()
    s = history.stats(
        history.fills(cfg.market, since(period), cfg.base.decimals, cfg.quote.decimals),
        cfg.base.decimals,
        cfg.quote.decimals,
        me,
    )
    b, q = cfg.base, cfg.quote
    d = {"base": b.symbol, "quote": q.symbol, "fills": s.fills, "volume": b.ui(s.volume), "notional": q.ui(s.notional)}
    if me:
        d |= {
            "bought": b.ui(s.bought),
            "avg_buy": s.avg_buy,
            "sold": b.ui(s.sold),
            "avg_sell": s.avg_sell,
            "net": b.ui(s.bought - s.sold),
        }
    emit_one(d, as_json, f"{cfg.name}, last {period}" + ("" if me else " — whole market"))


if __name__ == "__main__":
    typer.run(main)
