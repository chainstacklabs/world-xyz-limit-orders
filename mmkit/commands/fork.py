"""Practice on a local mainnet fork: start it, fund a wallet on it."""

import os
import shutil
from decimal import Decimal
from typing import Annotated

import typer

from mmkit import fork
from mmkit.config import rpc_url, wallet
from mmkit.guards import fork_only, is_local

app = typer.Typer(no_args_is_help=True, help=__doc__)
Amount = Annotated[Decimal | None, typer.Option(parser=Decimal)]


@app.command()
def start() -> None:
    """Run a surfpool fork of mainnet from your RPC_URL, in this terminal; point mm at it from another."""
    source = rpc_url()
    if is_local(source):
        raise SystemExit("RPC_URL points at a local RPC — fork start needs your mainnet RPC_URL to fork from")
    if not shutil.which("surfpool"):
        raise SystemExit("surfpool not found — install it: https://github.com/txtx/surfpool")
    print(
        f"forking mainnet from your RPC_URL on {fork.FORK_URL}\nin another terminal: RPC_URL={fork.FORK_URL} mm …   (then `mm fork fund`)",
        flush=True,
    )
    os.execvp("surfpool", fork.surfpool_args(source))


@app.command()
def fund(sol: Amount = None, cash: Amount = None) -> None:
    """Set the wallet's SOL and CASH on the fork, e.g. `mm fork fund --sol 2 --cash 100`."""
    fork_only(rpc_url())
    if sol is None and cash is None:
        raise SystemExit("give --sol, --cash or both")
    me = wallet().pubkey()
    fork.fund(me, None if sol is None else int(sol * 10**9), None if cash is None else int(cash * 10**6))
    print(f"{me} on the fork: " + ", ".join(f"{v} {k}" for k, v in (("SOL", sol), ("CASH", cash)) if v is not None))


if __name__ == "__main__":
    app()
