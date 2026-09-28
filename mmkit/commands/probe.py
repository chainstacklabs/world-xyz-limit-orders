"""Would World's router, or Jupiter, send a trade to your market?"""

from decimal import Decimal
from typing import Annotated

import typer

from mmkit import routes
from mmkit.common import Json, emit
from mmkit.config import load

HELP = "CASH to buy with and tokens to sell. A router sends the whole trade to one venue, so use a size your book can fill."
Size = Annotated[Decimal, typer.Option(parser=Decimal, help=HELP)]


def main(size: Size = Decimal(1), as_json: Json = False) -> None:
    """Buy and sell quotes from World's router and Jupiter: venue, whether it's your market, price."""
    cfg = load()
    title = f"{cfg.name} — {size} per quote; price in {cfg.quote.symbol} per {cfg.base.symbol}"
    emit(routes.probe(cfg, size), as_json, title)


if __name__ == "__main__":
    typer.run(main)
