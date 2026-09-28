"""Rows for `mm markets`: World's markets with status, question, public books and prices."""

import re
from concurrent.futures import ThreadPoolExecutor

from mmkit import books, world
from mmkit.common import text

ONE = 10**6  # 1 CASH or 1 outcome token; World mints use 6 decimals


def rows(windows: bool, status: str | None, search: str | None) -> list[dict]:
    ms = [m for m in world.list_markets() if (windows or m.end is None) and (not status or m.status() == status)]
    md = world.metadata([m.yes_mint for m in ms])
    ms = [m for m in ms if m.yes_mint in md]
    qs = world.questions({m.yes_mint: md[m.yes_mint]["uri"] for m in ms if m.end is None})
    idx = books.index()
    out = [
        {
            "ticker": md[m.yes_mint]["symbol"],
            "name": md[m.yes_mint]["name"],
            "question": qs.get(m.yes_mint),
            "status": m.status(),
            "ends": f"{m.end:%Y-%m-%d %H:%M}" if m.end else None,
            "books": len(idx.get(m.yes_mint, [])) + len(idx.get(m.no_mint, [])),
            "market": str(m.address),
            "_m": m,
            "_books": idx.get(m.yes_mint, []),
        }
        for m in ms
    ]
    return sorted(
        (r for r in out if not search or world.matches(r, search)), key=lambda r: (r["ticker"], r["ends"] or "~")
    )


def price(row: dict) -> dict:
    """World's buy/sell for 1 YES, and the first public book's best bid/ask in its own quote currency."""
    m = row["_m"]
    out = {"world_buy": world.buy_price(m, m.yes_mint), "world_sell": world.sell_price(m, m.yes_mint)}
    top = books.best(row["_books"][0].market) if row["_books"] else None
    return out | {
        "book_bid": top and top.bid,
        "book_ask": top and top.ask,
        "book_quote": top and books.symbol(top.quote_mint),
    }


def with_prices(rs: list[dict]) -> list[dict]:
    with ThreadPoolExecutor(8) as pool:
        return [r | p for r, p in zip(rs, pool.map(price, rs))]


def short(question: str | None) -> str | None:
    """The question without World's 'Resolves YES if … otherwise NO.' wrapper."""
    if not question:
        return question
    if m := re.fullmatch(r'Resolves YES if the answer to "(.+)" is yes; otherwise NO\.', question):
        return m[1]
    if m := re.fullmatch(r"Resolves YES if (.+); otherwise NO\.", question):
        return m[1]
    return question


def table_row(r: dict, prices: bool) -> dict:
    """The columns a person needs; `--json` keeps every field."""
    pair = lambda a, b, unit="": None if a is None and b is None else f"{text(a) or '—'} / {text(b) or '—'}{unit}"
    if prices:
        quote = f" {r['book_quote']}" if r.get("book_quote") else ""
        return {
            "ticker": r["ticker"],
            "status": r["status"],
            "ends": r["ends"],
            "world buy / sell": pair(r["world_buy"], r["world_sell"]),
            "book bid / ask": pair(r["book_bid"], r["book_ask"], quote) or ("empty" if r["books"] else None),
            "market": r["market"],
        }
    return {
        "ticker": r["ticker"],
        "question": (short(r["question"]) or "")[:60] or None,
        "status": r["status"],
        "ends": r["ends"],
        "books": r["books"] or None,
        "market": r["market"],
    }


def public(r: dict) -> dict:
    return {k: v for k, v in r.items() if not k.startswith("_")}
