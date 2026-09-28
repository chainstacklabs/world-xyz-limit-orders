"""What the wallet holds, and what sits in the market."""

from decimal import Decimal

import typer

from mmkit import rpc
from mmkit.common import Json, emit, read_market
from mmkit.config import load, wallet
from mmkit.spl import ata


def main(as_json: Json = False) -> None:
    """SOL and tokens in the wallet; free and resting amounts in the market."""
    cfg, me = load(), wallet().pubkey()
    b, q, no = cfg.base, cfg.quote, cfg.counterpart
    rows = [{"asset": "SOL", "wallet": Decimal(rpc.balance(me)) / 10**9, "free_in_market": None, "in_orders": None}]
    tokens = [b, no, q] + ([cfg.collateral] if cfg.collateral.mint != q.mint else [])
    rows += [
        {"asset": t.symbol, "wallet": t.ui(rpc.token_balance(ata(me, t))), "free_in_market": None, "in_orders": None}
        for t in tokens
    ]
    if cfg.market:
        m = read_market(cfg)
        seat = m.seat(me)
        rows[1] |= {
            "free_in_market": b.ui(seat.base_atoms if seat else 0),
            "in_orders": b.ui(sum(o.base_atoms for o in m.mine(me, False))),
        }
        rows[3] |= {
            "free_in_market": q.ui(seat.quote_atoms if seat else 0),
            "in_orders": q.ui(sum(o.locked_quote(round_up=True) for o in m.mine(me, True))),
        }
    emit(rows, as_json, str(me))


if __name__ == "__main__":
    typer.run(main)
