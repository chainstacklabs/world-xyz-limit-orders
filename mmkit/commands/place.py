"""Rest one limit order."""

import typer

from mmkit.common import Amount, Price, Send, Side, Yes, read_market, text, warn_if_crossing
from mmkit.config import load, wallet
from mmkit.sim import simulate_or_send
from mmkit.venue import manifest


def main(side: Side, size: Amount, price: Price, send: Send = False, yes: Yes = False) -> None:
    """Rest one order, depositing only what it needs, e.g. `mm place ask 10 0.05`."""
    cfg, me = load(), wallet()
    m = read_market(cfg)
    order = manifest.order(side == Side.bid, cfg.base.atoms(size), price, cfg.base, cfg.quote)
    print(f"{side.value} {text(size)} {cfg.base.symbol} @ {text(price)} {cfg.quote.symbol}")
    warn_if_crossing(m, side == Side.bid, price)
    simulate_or_send(manifest.place_ixs(m, cfg.market, me.pubkey(), cfg.base, cfg.quote, order), me, send, yes=yes)


if __name__ == "__main__":
    typer.run(main)
