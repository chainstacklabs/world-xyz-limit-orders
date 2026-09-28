import base64
import json
import struct
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from solders.pubkey import Pubkey
from typer.testing import CliRunner

from mmkit import books, cli, rpc, world
from mmkit.venue import manifest

from .conftest import PUBLIC_MARKET, WORLD_MARKET

# statuses — the fixture market's July window is over and it is resolved (274 and 283 set)


def with_window(data: bytes, start: datetime | None, end: datetime | None, opened: int, resolved: int) -> bytes:
    d = bytearray(data)
    ms = lambda t: int(t.timestamp() * 1000) if t else 0
    d[258:274] = struct.pack("<QQ", ms(start), ms(end))
    d[274], d[283] = opened, resolved
    return bytes(d)


def test_resolved(world_bytes):
    assert world.parse_market(WORLD_MARKET, world_bytes).status() == "resolved"


def test_statuses(world_bytes):
    now = datetime.now(UTC)
    cases = {
        "upcoming": (now + timedelta(hours=1), now + timedelta(hours=2), 0, 0),
        "live": (now - timedelta(minutes=1), now + timedelta(minutes=4), 1, 0),
        "ended": (now - timedelta(hours=2), now - timedelta(hours=1), 1, 0),
        "open": (None, None, 0, 0),
    }
    for status, args in cases.items():
        assert world.parse_market(WORLD_MARKET, with_window(world_bytes, *args)).status() == status, status


# public books


def slice_(base: Pubkey, quote: Pubkey) -> dict:
    return {"data": [base64.b64encode(bytes(base) + bytes(quote)).decode(), "base64"]}


def test_book_index_either_side(monkeypatch):
    yes, cash, usdc, other = (Pubkey.new_unique() for _ in range(4))
    accs = [
        {"pubkey": "11111111111111111111111111111112", "account": slice_(yes, cash)},
        {"pubkey": "11111111111111111111111111111113", "account": slice_(usdc, yes)},
        {"pubkey": "11111111111111111111111111111114", "account": slice_(other, usdc)},
    ]
    seen = {}
    monkeypatch.setattr(rpc, "call", lambda m, p: seen.update(opts=p[1]) or accs)
    idx = books.index()
    assert seen["opts"]["dataSlice"] == {"offset": 16, "length": 64}
    assert [(b.base_mint, b.quote_mint) for b in idx[yes]] == [(yes, cash), (usdc, yes)]
    assert other in idx and len(idx[other]) == 1


def test_best_prices(monkeypatch, market_bytes):
    monkeypatch.setattr(rpc, "account", lambda k: rpc.Account(market_bytes, 1, manifest.PROGRAM, False))
    monkeypatch.setattr(rpc, "slot", lambda: 1)
    top = books.best(PUBLIC_MARKET)
    assert (top.bid, top.ask) == (Decimal("0.000001"), Decimal(92))
    assert str(top.quote_mint) == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def test_symbol_of_known_quotes():
    assert books.symbol(world.CASH) == "CASH"
    assert books.symbol(Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")) == "USDC"
    assert books.symbol(Pubkey.from_string("11111111111111111111111111111112")) == "1111…1112"


# questions and search


def test_questions_are_fetched_once(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    a, b = Pubkey.new_unique(), Pubkey.new_unique()
    fetched = []
    monkeypatch.setattr(world, "description", lambda uri: fetched.append(uri) or f"Q {uri}")
    assert world.questions({a: "https://m/a", b: "https://m/b"}) == {a: "Q https://m/a", b: "Q https://m/b"}
    assert sorted(fetched) == ["https://m/a", "https://m/b"]
    fetched.clear()
    assert world.questions({a: "https://m/a"}) == {a: "Q https://m/a"} and fetched == []
    assert json.loads((tmp_path / "mm" / "questions.json").read_text())[str(a)] == "Q https://m/a"


def test_missing_questions_are_not_cached(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    a = Pubkey.new_unique()
    monkeypatch.setattr(world, "description", lambda uri: None)
    assert world.questions({a: "u"}) == {a: None}
    assert str(a) not in json.loads((tmp_path / "mm" / "questions.json").read_text())


@pytest.mark.parametrize(("text", "hit"), [("cpi", True), ("INFLATION", True), ("above 4.5", True), ("bitcoin", False)])
def test_search(text, hit):
    row = {"ticker": "CPI-A45-Y", "name": "Above 4.5% (Yes)", "question": "Will US CPI inflation exceed 4.5%?"}
    assert world.matches(row, text) is hit


# commands


def fake_world(monkeypatch, world_bytes):
    now = datetime.now(UTC)
    long_dated = world.parse_market(Pubkey.new_unique(), with_window(world_bytes, None, None, 0, 0))
    window = world.parse_market(
        Pubkey.new_unique(), with_window(world_bytes, now + timedelta(hours=1), now + timedelta(hours=2), 0, 0)
    )
    resolved = world.parse_market(Pubkey.new_unique(), world_bytes)
    ms = [fresh_mints(long_dated), fresh_mints(window), fresh_mints(resolved)]
    md = {m.yes_mint: {"symbol": t, "name": t, "uri": t} for m, t in zip(ms, ["CPI-A45-Y", "BTC-UP", "OLD-Y"])}
    monkeypatch.setattr(world, "list_markets", lambda: ms)
    monkeypatch.setattr(world, "metadata", lambda mints: md)
    monkeypatch.setattr(
        world,
        "questions",
        lambda uris: {m: ("Will CPI exceed 4.5%?" if md[m]["symbol"] == "CPI-A45-Y" else None) for m in uris},
    )
    monkeypatch.setattr(
        books, "index", lambda: {ms[0].yes_mint: [books.Book(PUBLIC_MARKET, ms[0].yes_mint, world.CASH)]}
    )
    return ms


def fresh_mints(m):
    return replace(m, yes_mint=Pubkey.new_unique(), no_mint=Pubkey.new_unique())


def test_markets_hides_windows_and_filters(monkeypatch, world_bytes):
    fake_world(monkeypatch, world_bytes)
    rows = json.loads(CliRunner().invoke(cli.app, ["markets", "--json"], env={}).stdout)
    assert [(r["ticker"], r["status"], r["books"]) for r in rows] == [("CPI-A45-Y", "open", 1)]  # windows hidden
    rows = json.loads(
        CliRunner().invoke(cli.app, ["markets", "--windows", "--status", "upcoming", "--json"], env={}).stdout
    )
    assert [r["ticker"] for r in rows] == ["BTC-UP"]
    rows = json.loads(
        CliRunner().invoke(cli.app, ["markets", "--windows", "--status", "resolved", "--json"], env={}).stdout
    )
    assert [r["ticker"] for r in rows] == ["OLD-Y"]
    rows = json.loads(CliRunner().invoke(cli.app, ["markets", "--search", "cpi 2027", "--json"], env={}).stdout)
    assert [r["ticker"] for r in rows] == []
    rows = json.loads(CliRunner().invoke(cli.app, ["markets", "--search", "exceed 4.5", "--json"], env={}).stdout)
    assert [r["ticker"] for r in rows] == ["CPI-A45-Y"]


def test_markets_prices_are_capped(monkeypatch, world_bytes):
    fake_world(monkeypatch, world_bytes)
    quoted = []
    monkeypatch.setattr(world, "router_quote", lambda a, b, atoms: quoted.append(a) or 3_000_000)
    monkeypatch.setattr(books, "best", lambda k: books.Top(Decimal("0.2"), Decimal("0.4"), world.CASH))
    rows = json.loads(CliRunner().invoke(cli.app, ["markets", "--prices", "--limit", "1", "--json"], env={}).stdout)
    assert len(rows) == 1 and len(quoted) == 2  # one buy, one sell quote for the one row shown
    assert rows[0]["world_buy"] == "0.3333" and rows[0]["world_sell"] == "3"
    assert rows[0]["book_bid"] == "0.2" and rows[0]["book_ask"] == "0.4" and rows[0]["book_quote"] == "CASH"


def test_market_shows_status_and_books(monkeypatch, world_bytes):
    from mmkit.commands import market

    m = world.parse_market(WORLD_MARKET, world_bytes)
    monkeypatch.setattr(rpc, "account", lambda k: rpc.Account(world_bytes, 1, world.PROGRAM, False))
    monkeypatch.setattr(rpc, "token_balance", lambda k: 5_000_000)
    monkeypatch.setattr(world, "metadata", lambda mints: {x: {"symbol": "T", "name": "T", "uri": "u"} for x in mints})
    monkeypatch.setattr(world, "description", lambda uri: "Q")
    monkeypatch.setattr(world, "router_quote", lambda a, b, atoms: None)
    monkeypatch.setattr(market.books, "index", lambda: {m.no_mint: [books.Book(PUBLIC_MARKET, m.no_mint, world.CASH)]})
    monkeypatch.setattr(books, "best", lambda k: books.Top(Decimal("0.6"), None, world.CASH))
    out = json.loads(CliRunner().invoke(cli.app, ["market", str(WORLD_MARKET), "--json"], env={}).stdout)
    assert out["status"] == "resolved"
    assert out["books"] == [f"{PUBLIC_MARKET} NO/CASH bid 0.6 ask —"]


def test_markets_table_is_compact(monkeypatch, world_bytes):
    fake_world(monkeypatch, world_bytes)
    monkeypatch.setattr(world, "router_quote", lambda a, b, atoms: 3_000_000)
    monkeypatch.setattr(books, "best", lambda k: books.Top(Decimal("0.2"), Decimal("0.4"), world.CASH))
    plain = CliRunner().invoke(cli.app, ["markets"], env={"COLUMNS": "200"}).output
    header = plain.splitlines()[2]
    assert "question" in header and "name" not in header and "ends" not in header  # all-empty column dropped
    priced = CliRunner().invoke(cli.app, ["markets", "--prices"], env={"COLUMNS": "200"}).output
    assert "0.3333 / 3" in priced and "0.2 / 0.4 CASH" in priced and "question" not in priced


def test_emit_drops_empty_columns(capsys):
    from mmkit import common

    common.emit([{"a": 1, "b": None}, {"a": 2, "b": None}], False)
    out = capsys.readouterr().out
    assert " a " in out and " b " not in out


@pytest.mark.parametrize(
    ("full", "short"),
    [
        (
            'Resolves YES if the answer to "Will Donald Trump win the 2028 election?" is yes; otherwise NO.',
            "Will Donald Trump win the 2028 election?",
        ),
        (
            "Resolves YES if Nico Hulkenberg wins Sao Paulo Grand Prix 2026; otherwise NO.",
            "Nico Hulkenberg wins Sao Paulo Grand Prix 2026",
        ),
        (
            "BTC/USD closes at or above its open between A and B.",
            "BTC/USD closes at or above its open between A and B.",
        ),
        (None, None),
    ],
)
def test_short_question(full, short):
    from mmkit import discovery

    assert discovery.short(full) == short
