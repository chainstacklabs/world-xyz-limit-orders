"""Your open orders."""

import typer

from mmkit.common import Json, emit, read_market
from mmkit.config import load, wallet


def main(as_json: Json = False) -> None:
    """Your resting orders, with the id `amend` and `cancel` take."""
    cfg, me = load(), wallet().pubkey()
    m = read_market(cfg)
    mine = sorted(m.mine(me, False) + m.mine(me, True), key=lambda o: -o.price)
    rows = [
        {
            "id": o.seq,
            "side": "bid" if o.is_bid else "ask",
            "size": cfg.base.ui(o.base_atoms),
            "price": o.price,
            "value": cfg.base.ui(o.base_atoms) * o.price,
        }
        for o in mine
    ]
    emit(rows, as_json, f"open orders — {cfg.name}")


if __name__ == "__main__":
    typer.run(main)
