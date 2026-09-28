"""mm — place and manage your own limit orders on World outcome tokens."""

import typer

from mmkit.commands import (
    amend,
    book,
    cancel,
    close,
    create,
    exit,
    fills,
    fork,
    market,
    markets,
    merge,
    orders,
    place,
    probe,
    reprice,
    simulate_fill,
    split,
    stats,
    swap,
    use,
    verify,
    wallet,
    withdraw,
)

READ = (markets, market, use, verify, wallet, book, orders, fills, stats, probe, simulate_fill)
WRITE = (swap, split, merge, close, create, place, amend, cancel, reprice, withdraw, exit)

app = typer.Typer(no_args_is_help=True, add_completion=False, pretty_exceptions_enable=False, help=__doc__)
for command in READ + WRITE:
    app.command(command.__name__.rsplit(".", 1)[1].replace("_", "-"))(command.main)
app.add_typer(fork.app, name="fork")


def run() -> None:
    app()  # errors are SystemExit (rpc.RpcError included): one line on stderr
