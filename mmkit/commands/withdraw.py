"""Withdraw free funds from the market; your orders stay."""

from enum import Enum

import typer

from mmkit.common import Send, Yes, read_market
from mmkit.config import load, wallet
from mmkit.sim import simulate_or_send
from mmkit.venue import manifest


class Which(str, Enum):
    base = "base"
    quote = "quote"


def main(
    which: Which,
    amount: str = typer.Argument(help='Amount, or "all" that is free'),
    send: Send = False,
    yes: Yes = False,
) -> None:
    """Withdraw what is free in the market (not resting in orders), e.g. `mm withdraw quote 5`."""
    cfg = load()
    token = cfg.base if which == Which.base else cfg.quote
    atoms = None if amount == "all" else token.atoms(amount)
    me = wallet()
    ixs = manifest.withdraw_free_ixs(read_market(cfg), cfg.market, me.pubkey(), token, which == Which.base, atoms)
    print(f"withdraw {amount} {token.symbol} to the wallet")
    simulate_or_send(ixs, me, send, yes=yes)


if __name__ == "__main__":
    typer.run(main)
