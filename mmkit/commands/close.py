"""Close empty YES/NO token accounts."""

import typer

from mmkit import rpc
from mmkit.common import Send, Yes
from mmkit.config import load, wallet
from mmkit.sim import simulate_or_send
from mmkit.spl import ata, close_empty


def main(send: Send = False, yes: Yes = False) -> None:
    """Close the wallet's empty base and counterpart token accounts and get their rent back."""
    cfg, me = load(), wallet()

    def balance(t) -> int | None:
        a = rpc.account(ata(me.pubkey(), t))
        return None if a is None else int.from_bytes(a.data[64:72], "little")

    ixs = close_empty(me.pubkey(), [(t, balance(t)) for t in (cfg.base, cfg.counterpart)])
    if not ixs:
        raise SystemExit("no empty token accounts to close")
    print(f"close {len(ixs)} empty token account(s)")
    simulate_or_send(ixs, me, send, yes=yes)


if __name__ == "__main__":
    typer.run(main)
