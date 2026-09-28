"""Cancel everything and withdraw."""

import typer

from mmkit.common import Send, Yes, read_market
from mmkit.config import load, wallet
from mmkit.sim import simulate_or_send
from mmkit.venue import manifest


def main(send: Send = False, yes: Yes = False) -> None:
    """Cancel all your orders and withdraw everything to the wallet. A dry run withdraws only what is already free."""
    cfg, me = load(), wallet()
    m = read_market(cfg)
    cancel = manifest.cancel_all_ixs(m, cfg.market, me.pubkey())
    if cancel:
        print(f"cancel {len(m.mine(me.pubkey(), True) + m.mine(me.pubkey(), False))} orders")
        simulate_or_send(cancel, me, send, yes=yes)
        m = read_market(cfg) if send else m
    withdraw = manifest.withdraw_all_ixs(m, cfg.market, me.pubkey(), cfg.base, cfg.quote)
    seat = m.seat(me.pubkey())
    if withdraw and seat:
        print(
            f"withdraw {cfg.base.ui(seat.base_atoms)} {cfg.base.symbol}, {cfg.quote.ui(seat.quote_atoms)} {cfg.quote.symbol}"
        )
        simulate_or_send(withdraw, me, send, yes=yes)
    print("the market account and its rent stay behind — Manifest has no close instruction")


if __name__ == "__main__":
    typer.run(main)
