"""Both sides of the book."""

import os

import typer

from mmkit.common import Json, emit, read_market
from mmkit.config import load, wallet


def main(as_json: Json = False) -> None:
    """Every resting order, asks above bids; yours marked."""
    cfg = load()
    m = read_market(cfg)
    me = wallet().pubkey() if os.environ.get("WALLET_KEY") else None
    row = lambda side, o: {
        "side": side,
        "size": cfg.base.ui(o.base_atoms),
        "price": o.price,
        "id": o.seq,
        "yours": o.trader == me,
    }
    rows = [row("ask", o) for o in reversed(m.asks)] + [row("bid", o) for o in m.bids]
    emit(rows, as_json, f"{cfg.name}  spare block: {'yes' if m.has_free_block else 'no'}")


if __name__ == "__main__":
    typer.run(main)
