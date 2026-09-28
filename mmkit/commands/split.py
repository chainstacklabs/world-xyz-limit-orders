"""Mint complete sets: N CASH -> N YES + N NO."""

import typer

from mmkit import issuer
from mmkit.common import Amount, Send, Yes
from mmkit.config import load, wallet
from mmkit.sim import simulate_or_send
from mmkit.spl import create_ata


def main(amount: Amount, send: Send = False, yes: Yes = False) -> None:
    """Lock N CASH with the issuer and get N YES + N NO."""
    cfg = load()
    atoms = cfg.collateral.atoms(amount)
    me = wallet()
    n = cfg.collateral.ui(atoms)
    print(f"{n} {cfg.collateral.symbol} -> {n} {cfg.yes.symbol} + {n} {cfg.no.symbol}")
    ixs = [
        create_ata(me.pubkey(), cfg.base),
        create_ata(me.pubkey(), cfg.counterpart),
        issuer.split(cfg, me.pubkey(), atoms),
    ]
    simulate_or_send(ixs, me, send, yes=yes)


if __name__ == "__main__":
    typer.run(main)
