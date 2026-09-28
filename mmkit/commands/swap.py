"""SOL <-> CASH through Jupiter."""

from enum import Enum

import typer

from mmkit import jupiter, world
from mmkit.common import Amount, Send, Yes
from mmkit.config import Token, wallet
from mmkit.sim import sign_and_run
from mmkit.spl import TOKEN_2022_PROGRAM, TOKEN_PROGRAM


class Asset(str, Enum):
    sol = "sol"
    cash = "cash"


TOKENS = {
    Asset.sol: Token("SOL", jupiter.SOL, 9, TOKEN_PROGRAM),
    Asset.cash: Token("CASH", world.CASH, 6, TOKEN_2022_PROGRAM),
}


def main(sell: Asset, buy: Asset, amount: Amount, send: Send = False, yes: Yes = False) -> None:
    """Swap SOL for CASH or back, e.g. `mm swap sol cash 0.5`."""
    if sell == buy:
        raise SystemExit("pick two different assets")
    a, b = TOKENS[sell], TOKENS[buy]
    atoms = a.atoms(amount)
    me = wallet()
    q = jupiter.quote(a.mint, b.mint, atoms)
    print(f"{a.ui(atoms)} {a.symbol} -> {b.ui(int(q['outAmount']))} {b.symbol}  (price impact {q['priceImpactPct']}%)")
    sign_and_run(jupiter.swap_tx(q, me.pubkey()), me, send, yes=yes)


if __name__ == "__main__":
    typer.run(main)
