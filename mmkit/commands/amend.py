"""Change one order's price or size."""

from decimal import Decimal
from typing import Annotated

import typer

from mmkit.common import Send, Yes, read_market, text, warn_if_crossing
from mmkit.config import load, wallet
from mmkit.sim import simulate_or_send
from mmkit.venue import manifest

Opt = Annotated[Decimal | None, typer.Option(parser=Decimal)]


def main(order_id: int, price: Opt = None, size: Opt = None, send: Send = False, yes: Yes = False) -> None:
    """Cancel an order and replace it in one transaction, e.g. `mm amend 42 --price 0.06`."""
    if price is None and size is None:
        raise SystemExit("give --price, --size or both")
    cfg, me = load(), wallet()
    m = read_market(cfg)
    atoms = None if size is None else cfg.base.atoms(size)
    ixs = manifest.amend_ixs(m, cfg.market, me.pubkey(), cfg.base, cfg.quote, order_id, atoms, price)
    changes = [f"{k} {text(v)}" for k, v in (("size", size), ("price", price)) if v is not None]
    print(f"order {order_id} -> {', '.join(changes)}")
    old = next(o for o in m.mine(me.pubkey(), True) + m.mine(me.pubkey(), False) if o.seq == order_id)
    warn_if_crossing(m, old.is_bid, old.price if price is None else price)
    simulate_or_send(ixs, me, send, yes=yes)


if __name__ == "__main__":
    typer.run(main)
