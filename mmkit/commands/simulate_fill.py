"""Would your book fill if someone took it right now?"""

from typing import Annotated

import typer
from solders.pubkey import Pubkey

from mmkit import taker
from mmkit.common import Amount, Json, Side, emit_one, read_market
from mmkit.config import load

Taker = Annotated[
    str | None, typer.Option("--taker", help="Wallet to simulate as the taker; default: a large holder with SOL")
]


def main(side: Side, size: Amount, taker_key: Taker = None, as_json: Json = False) -> None:
    """Simulate a taker filling your bids (they sell) or asks (they buy). Nothing is signed or sent."""
    cfg = load()
    m = read_market(cfg)
    is_bid = side == Side.bid
    atoms = cfg.base.atoms(size)
    need = (cfg.base.mint, atoms) if is_bid else (cfg.quote.mint, 1)
    who = Pubkey.from_string(taker_key) if taker_key else taker.find_taker(*need)
    f = taker.simulate_fill(m, cfg.market, cfg.base, cfg.quote, is_bid, atoms, who)
    pay, get = (cfg.base, cfg.quote) if is_bid else (cfg.quote, cfg.base)
    emit_one(
        {
            "taker": str(who),
            "fills": f.error is None,
            "spent": f"{pay.ui(f.spent)} {pay.symbol}",
            "received": f"{get.ui(f.received)} {get.symbol}",
            "avg_price": f.avg_price,
            "taker_pays_for_growth": f.market_grew,
            "error": f.error,
            "logs": f.logs or None,
        },
        as_json,
        f"a taker {'selling into your bids' if is_bid else 'buying your asks'} — simulated, not sent",
    )


if __name__ == "__main__":
    typer.run(main)
