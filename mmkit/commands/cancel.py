"""Cancel orders."""

from typing import Annotated

import typer

from mmkit.common import Send, Yes, read_market
from mmkit.config import load, wallet
from mmkit.sim import simulate_or_send
from mmkit.venue import manifest


def main(
    order_ids: Annotated[list[str], typer.Argument(help='Order ids from `mm orders`, or "all"')],
    send: Send = False,
    yes: Yes = False,
) -> None:
    """Cancel orders by id, or all of yours. Funds stay in the market until `mm exit`."""
    if order_ids != ["all"] and (bad := [i for i in order_ids if not i.isdigit()]):
        raise SystemExit(f"not an order id: {bad[0]} — see `mm orders`")
    cfg, me = load(), wallet()
    m = read_market(cfg)
    if order_ids == ["all"]:
        ixs = manifest.cancel_all_ixs(m, cfg.market, me.pubkey())
    else:
        ixs = manifest.cancel_ixs(m, cfg.market, me.pubkey(), [int(i) for i in order_ids])
    if not ixs:
        raise SystemExit("you have no open orders")
    simulate_or_send(ixs, me, send, yes=yes)


if __name__ == "__main__":
    typer.run(main)
