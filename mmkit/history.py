"""Fills on a market over a period, and what they add up to."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from solders.pubkey import Pubkey

from mmkit import rpc
from mmkit.venue import manifest


def fills(market: Pubkey, since: datetime, base_decimals: int, quote_decimals: int) -> list[manifest.Fill]:
    """Every fill on the market since `since`, newest first."""
    out, before = [], None
    while True:
        sigs = rpc.call(
            "getSignaturesForAddress", [str(market), {"limit": 1000, **({"before": before} if before else {})}]
        )
        for s in sigs:
            if s["blockTime"] is None:
                continue
            when = datetime.fromtimestamp(s["blockTime"], UTC)
            if when < since:
                return out
            tx = (
                rpc.call("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
                if s["err"] is None
                else None
            )
            if tx:
                logs = tx["meta"]["logMessages"] or []
                out += [
                    f
                    for f in manifest.parse_fills(logs, base_decimals, quote_decimals, s["signature"], when)
                    if f.market == market
                ]
        if len(sigs) < 1000:
            return out
        before = sigs[-1]["signature"]


@dataclass(frozen=True)
class Stats:
    fills: int
    volume: int  # base atoms
    notional: int  # quote atoms
    bought: int  # base atoms the maker bought: their bids filled
    sold: int
    avg_buy: Decimal | None
    avg_sell: Decimal | None


def stats(fs: list[manifest.Fill], base_decimals: int, quote_decimals: int, maker: Pubkey | None = None) -> Stats:
    fs = [f for f in fs if maker is None or f.maker == maker]
    buys = [f for f in fs if not f.taker_is_buy]
    sells = [f for f in fs if f.taker_is_buy]
    scale = Decimal(10) ** (base_decimals - quote_decimals)

    def avg(side: list[manifest.Fill]) -> Decimal | None:
        base = sum(f.base_atoms for f in side)
        return Decimal(sum(f.quote_atoms for f in side)) / base * scale if base else None

    return Stats(
        fills=len(fs),
        volume=sum(f.base_atoms for f in fs),
        notional=sum(f.quote_atoms for f in fs),
        bought=sum(f.base_atoms for f in buys),
        sold=sum(f.base_atoms for f in sells),
        avg_buy=avg(buys),
        avg_sell=avg(sells),
    )
