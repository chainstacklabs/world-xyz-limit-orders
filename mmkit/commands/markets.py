"""List World markets."""

from typing import Annotated

import typer

from mmkit import discovery
from mmkit.common import Json, emit

Status = typer.Option(help="upcoming, live, ended, resolved or open")


def main(
    search: Annotated[str | None, typer.Option(help="Match ticker, name or question, e.g. inflation")] = None,
    status: Annotated[str | None, Status] = None,
    windows: Annotated[bool, typer.Option("--windows", help="Include the 5/15/60-minute crypto windows.")] = False,
    prices: Annotated[
        bool, typer.Option("--prices", help="Add World's prices and the best public book prices.")
    ] = False,
    limit: Annotated[int, typer.Option(help="Show at most this many rows.")] = 50,
    as_json: Json = False,
) -> None:
    """List World markets: ticker, question, status, window end, public books, address."""
    rs = discovery.rows(windows, status, search)
    shown = discovery.with_prices(rs[:limit]) if prices else rs[:limit]
    if not as_json:
        shown = [discovery.table_row(r, prices) for r in shown]
    more = f" — showing {len(shown)}; narrow with --search or raise --limit" if len(rs) > len(shown) else ""
    emit([discovery.public(r) for r in shown], as_json, f"World markets ({len(rs)}){more}")


if __name__ == "__main__":
    typer.run(main)
