"""Simulate someone taking your orders: what fills, at what price, and who pays for growth."""

import base64
import math
from dataclasses import dataclass, field
from decimal import Context, Decimal

from solders.hash import Hash
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import Transaction

from mmkit import rpc
from mmkit.config import Token
from mmkit.spl import SYSTEM_PROGRAM, ata, create_ata
from mmkit.venue import manifest

FEE_RESERVE = 10_000_000  # lamports a borrowed taker needs for fees and new token accounts
PRICE = Context(prec=10)  # significant digits in a reported average price


def find_taker(mint: Pubkey, min_atoms: int) -> Pubkey:
    """The largest holder of `mint` that is a plain wallet with SOL for fees."""
    try:
        largest = rpc.call("getTokenLargestAccounts", [str(mint), {"commitment": "confirmed"}])["value"]
    except rpc.RpcError:
        raise SystemExit(f"this RPC can't list the largest holders of {mint} — pass --taker") from None
    accounts = [a["address"] for a in largest if int(a["amount"]) >= min_atoms]
    if not accounts:
        raise SystemExit(f"no wallet holds enough {mint} to take this — pass --taker")
    infos = rpc.call("getMultipleAccounts", [accounts, {"encoding": "jsonParsed"}])["value"]
    owners = [i["data"]["parsed"]["info"]["owner"] for i in infos if i]
    wallets = rpc.call(
        "getMultipleAccounts", [owners, {"encoding": "base64", "dataSlice": {"offset": 0, "length": 0}}]
    )["value"]
    for owner, w in zip(owners, wallets):
        if w and w["owner"] == str(SYSTEM_PROGRAM) and w["lamports"] >= FEE_RESERVE:
            return Pubkey.from_string(owner)
    raise SystemExit("no plain wallet with SOL among the largest holders — pass --taker")


@dataclass(frozen=True)
class Fill:
    spent: int
    received: int
    avg_price: Decimal | None
    market_grew: bool
    error: str | None = None
    logs: list[str] = field(default_factory=list)


def _amount(acc: dict) -> int:
    return int.from_bytes(base64.b64decode(acc["data"][0])[64:72], "little")


def simulate_fill(
    m: manifest.Market, market: Pubkey, base: Token, quote: Token, is_bid: bool, size: int, taker: Pubkey
) -> Fill:
    """is_bid: a taker sells `size` base into your bids; else buys `size` base from your asks."""
    side = m.bids if is_bid else m.asks
    if not side:
        raise SystemExit(f"no {'bids' if is_bid else 'asks'} to fill")
    if is_bid:
        in_atoms = size
    else:  # quote needed to buy `size` base, walking the asks best first
        left, in_atoms = size, 0
        for o in side:
            take = min(left, o.base_atoms)
            in_atoms += math.ceil(take * o.price_d18 / 10**18)
            left -= take
            if not left:
                break
    ixs = [create_ata(taker, quote if is_bid else base), manifest.swap(taker, market, base, quote, in_atoms, 0, is_bid)]
    raw = base64.b64encode(
        bytes(Transaction.new_unsigned(Message.new_with_blockhash(ixs, taker, Hash.default())))
    ).decode()
    watch = [ata(taker, base), ata(taker, quote), market]
    before_base, before_quote = rpc.token_balance(watch[0]), rpc.token_balance(watch[1])
    before = rpc.account(market)
    opts = {
        "encoding": "base64",
        "sigVerify": False,
        "replaceRecentBlockhash": True,
        "commitment": "confirmed",
        "accounts": {"encoding": "base64", "addresses": [str(k) for k in watch]},
    }
    sim = rpc.call("simulateTransaction", [raw, opts])["value"]
    if sim["err"]:
        return Fill(0, 0, None, False, str(sim["err"]), (sim.get("logs") or [])[-5:])
    after_base, after_quote, after_market = sim["accounts"]
    base_moved, quote_moved = abs(_amount(after_base) - before_base), abs(_amount(after_quote) - before_quote)
    spent, received = (base_moved, quote_moved) if is_bid else (quote_moved, base_moved)
    avg = (
        PRICE.create_decimal(Decimal(quote_moved) / base_moved * Decimal(10) ** (base.decimals - quote.decimals))
        if base_moved
        else None
    )
    grew = after_market["lamports"] > before.lamports or after_market["space"] > len(before.data)
    return Fill(spent, received, avg, grew)
