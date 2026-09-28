"""Move one whole side to a new price."""

import typer

from mmkit.common import Price, Send, Side, Yes, read_market, text, warn_if_crossing
from mmkit.config import load, wallet
from mmkit.sim import simulate_or_send
from mmkit.venue import manifest


def main(side: Side, price: Price, send: Send = False, yes: Yes = False) -> None:
    """Cancel your orders on one side and rest everything that side holds at one price, atomically."""
    cfg, me = load(), wallet()
    m = read_market(cfg)
    is_bid = side == Side.bid
    cancels, new = manifest.reprice(m, me.pubkey(), cfg.base, cfg.quote, is_bid, price)
    print(
        f"cancel {len(cancels)} {side.value}(s), rest {text(cfg.base.ui(new.base_atoms))} {cfg.base.symbol} @ {text(price)}"
    )
    warn_if_crossing(m, is_bid, price)
    simulate_or_send(
        manifest.reprice_ixs(m, cfg.market, me.pubkey(), cfg.base, cfg.quote, is_bid, price), me, send, yes=yes
    )


if __name__ == "__main__":
    typer.run(main)
