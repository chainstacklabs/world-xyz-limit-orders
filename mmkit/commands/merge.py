"""Redeem complete sets: N YES + N NO -> N CASH."""

import typer

from mmkit import issuer, rpc
from mmkit.common import Send, Yes
from mmkit.config import load, wallet
from mmkit.sim import simulate_or_send
from mmkit.spl import ata


def main(amount: str = typer.Argument(help='Sets to redeem, or "max"'), send: Send = False, yes: Yes = False) -> None:
    """Give back equal base and counterpart, get quote tokens. Needs both sides."""
    cfg, me = load(), wallet()
    base_held, counterpart_held = (rpc.token_balance(ata(me.pubkey(), t)) for t in (cfg.base, cfg.counterpart))
    held = min(base_held, counterpart_held)
    atoms = held if amount == "max" else cfg.collateral.atoms(amount)
    if not 0 < atoms <= held:
        raise SystemExit(
            f"you can merge at most {cfg.base.ui(held)} — the smaller of your {cfg.base.symbol} and {cfg.counterpart.symbol}"
        )
    print(
        f"{cfg.base.ui(atoms)} {cfg.base.symbol} + {cfg.counterpart.symbol} -> {cfg.collateral.ui(atoms)} {cfg.collateral.symbol}"
    )
    simulate_or_send(issuer.merge_ixs(cfg, me.pubkey(), atoms, base_held, counterpart_held), me, send, yes=yes)


if __name__ == "__main__":
    typer.run(main)
