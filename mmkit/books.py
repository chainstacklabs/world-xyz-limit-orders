"""Public order books for World tokens: every Manifest market, in any quote currency."""

import base64
from dataclasses import dataclass
from decimal import Decimal

from solders.pubkey import Pubkey

from mmkit import rpc
from mmkit.config import Token
from mmkit.venue import manifest

KNOWN = {
    Pubkey.from_string("CASHx9KJUStyftLFWGvEVf59SGeG9sh5FfcnZMVPCASH"): "CASH",
    Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"): "USDC",
    Pubkey.from_string("So11111111111111111111111111111111111111112"): "SOL",
}


@dataclass(frozen=True)
class Book:
    market: Pubkey
    base_mint: Pubkey
    quote_mint: Pubkey


@dataclass(frozen=True)
class Top:
    bid: Decimal | None
    ask: Decimal | None
    quote_mint: Pubkey


def index() -> dict[Pubkey, list[Book]]:
    """Every Manifest market, filed under both of its mints."""
    opts = {"encoding": "base64", "dataSlice": {"offset": 16, "length": 64}}  # base mint, quote mint
    out: dict[Pubkey, list[Book]] = {}
    for a in rpc.call("getProgramAccounts", [str(manifest.PROGRAM), opts]):
        d = base64.b64decode(a["account"]["data"][0])
        book = Book(Pubkey.from_string(a["pubkey"]), Pubkey.from_bytes(d[:32]), Pubkey.from_bytes(d[32:64]))
        for mint in (book.base_mint, book.quote_mint):
            out.setdefault(mint, []).append(book)
    return out


def best(market: Pubkey) -> Top:
    m = manifest.parse(rpc.account(market).data, rpc.slot())
    return Top(m.bids[0].price if m.bids else None, m.asks[0].price if m.asks else None, m.quote_mint)


def symbol(mint: Pubkey) -> str:
    s = str(mint)
    return KNOWN.get(mint) or f"{s[:4]}…{s[-4:]}"


def describe(b: Book, labels: dict[Pubkey, str]) -> str:
    """One line: the book, its pair, best bid and ask in its own quote currency."""
    top = best(b.market)
    pair = "/".join(labels.get(x) or symbol(x) for x in (b.base_mint, b.quote_mint))
    price = lambda v: format(v.normalize(), "f") if v is not None else "—"
    return f"{b.market} {pair} bid {price(top.bid)} ask {price(top.ask)}"


def token(mint: str) -> Token:
    """A quote currency from its mint: decimals and token program read from chain."""
    key = Pubkey.from_string(mint)
    acc = rpc.account(key)
    if acc is None:
        raise SystemExit(f"{mint} is not a token mint")
    return Token(symbol(key), key, acc.data[44], acc.owner)  # decimals sit at byte 44 of a mint
