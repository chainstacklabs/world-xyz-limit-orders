"""What the commands share: options, output, reading the configured market."""

import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from mmkit import rpc
from mmkit.config import Config, require_market
from mmkit.venue import manifest

Send = Annotated[bool, typer.Option("--send", help="Execute. Without it the transaction is only simulated.")]
Yes = Annotated[bool, typer.Option("--yes", "-y", help="With --send: send without asking (scripts, agents).")]
Json = Annotated[bool, typer.Option("--json", help="Machine-readable output.")]
Amount = Annotated[Decimal, typer.Argument(parser=Decimal, help="Token amount, e.g. 10 or 2.5")]
Price = Annotated[Decimal, typer.Argument(parser=Decimal, help="Quote tokens per base token, e.g. 0.05")]


class Side(str, Enum):
    bid = "bid"
    ask = "ask"


def read_market(cfg: Config) -> manifest.Market:
    key = require_market(cfg)
    acc = rpc.account(key)
    if acc is None or acc.owner != manifest.PROGRAM:
        raise SystemExit(f"{key} is not a Manifest market — check venue.market in market.json")
    m = manifest.parse(acc.data, rpc.slot())
    if (m.base_mint, m.quote_mint) != (cfg.base.mint, cfg.quote.mint):
        raise SystemExit(f"{key} is a Manifest market for another pair — check venue.market in market.json")
    return m


def warn_if_crossing(m: manifest.Market, is_bid: bool, price: Decimal) -> None:
    if manifest.crosses(m, is_bid, price):
        other = m.asks[0] if is_bid else m.bids[0]
        print(
            f"warning: {text(price)} crosses the book (best {'ask' if is_bid else 'bid'} {text(other.price)}) — it fills at once"
        )


def since(period: str) -> datetime:
    m = re.fullmatch(r"(\d+)([mhd])", period)
    if not m:
        raise typer.BadParameter("use a number and m, h or d — e.g. 30m, 24h, 7d")
    return datetime.now(UTC) - timedelta(**{{"m": "minutes", "h": "hours", "d": "days"}[m[2]]: int(m[1])})


def text(v) -> str:
    """Decimals without trailing zeros or exponents; empty for None."""
    if v is None:
        return ""
    if isinstance(v, datetime):
        return f"{v:%Y-%m-%d %H:%M} UTC"
    if isinstance(v, list):
        return ", ".join(map(str, v)) or "none"
    return format(v.normalize(), "f") if isinstance(v, Decimal) else str(v)


def emit_one(d: dict, as_json: bool, title: str | None = None) -> None:
    """One record: field / value for people, a JSON object for scripts."""
    if as_json:
        print(json.dumps({k: text(v) if isinstance(v, (Decimal, datetime)) else v for k, v in d.items()}, indent=1))
        return
    if title:
        print(title)
    table = Table(show_header=False)
    table.add_column()
    table.add_column(overflow="fold")
    for k, v in d.items():
        table.add_row(k, text(v))
    Console().print(table)


def emit(rows: list[dict], as_json: bool, title: str | None = None) -> None:
    """A table for people, JSON for scripts and agents."""
    if as_json:
        print(
            json.dumps(
                [{k: text(v) if isinstance(v, Decimal) else v for k, v in r.items()} for r in rows],
                default=str,
                indent=1,
            )
        )
        return
    if title:
        print(title)
    if not rows:
        print("  none")
        return
    cols = [c for c in rows[0] if any(r.get(c) is not None for r in rows)]  # drop columns empty on every row
    rows = [{c: r.get(c) for c in cols} for r in rows]
    table = Table()
    for col in rows[0]:
        table.add_column(col, justify="right" if isinstance(rows[0][col], (int, Decimal)) else "left", overflow="fold")
    for row in rows:
        table.add_row(*map(text, row.values()))
    Console().print(table)
