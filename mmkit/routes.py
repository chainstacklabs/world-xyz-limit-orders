"""Which venue would a router send a trade to? Quotes only; nothing is built or signed."""

from dataclasses import dataclass, field
from decimal import Decimal
from urllib.parse import urlencode

from solders.pubkey import Pubkey

from mmkit.config import Config
from mmkit.jupiter import API as JUPITER
from mmkit.jupiter import SOL
from mmkit.web import get_json
from mmkit.world import CASH, ROUTER_HEADERS
from mmkit.world import ROUTER as WORLD


@dataclass(frozen=True)
class Leg:
    venue: str
    key: Pubkey


@dataclass(frozen=True)
class Route:
    router: str
    side: str
    legs: list[Leg] = field(default_factory=list)
    in_atoms: int = 0
    out_atoms: int = 0
    error: str | None = None

    def yours(self, market: Pubkey | None) -> bool:
        return market is not None and any(leg.key == market for leg in self.legs)


def parse(router: str, side: str, body: dict) -> Route:
    if "outAmount" not in body:
        return Route(router, side, error=str(body.get("errorCode") or body.get("code") or body.get("error") or body))
    legs = [
        Leg(r["venue"], Pubkey.from_string(r["marketKey"]))
        if "venue" in r
        else Leg(r["swapInfo"]["label"], Pubkey.from_string(r["swapInfo"]["ammKey"]))
        for r in body.get("routePlan", [])
    ]
    return Route(router, side, legs, int(body["inAmount"]), int(body["outAmount"]))


def _quote(router: str, side: str, url: str, headers: dict | None) -> Route:
    try:
        return parse(router, side, get_json(url, headers))
    except SystemExit as e:
        return Route(router, side, error=str(e.code).rsplit(": ", 1)[-1])


def _params(input_mint: Pubkey, output_mint: Pubkey, atoms: int) -> str:
    return urlencode(
        {"inputMint": str(input_mint), "outputMint": str(output_mint), "amount": atoms, "slippageBps": 100}
    )


def world(input_mint: Pubkey, output_mint: Pubkey, atoms: int, side: str = "") -> Route:
    return _quote("world", side, f"{WORLD}?{_params(input_mint, output_mint, atoms)}", ROUTER_HEADERS)


def jupiter(input_mint: Pubkey, output_mint: Pubkey, atoms: int, side: str = "") -> Route:
    return _quote("jupiter", side, f"{JUPITER}/quote?{_params(input_mint, output_mint, atoms)}", None)


def probe(cfg: Config, size: Decimal) -> list[dict]:
    """Buy and sell quotes for `size` from World's router and Jupiter, plus a control quote."""
    b, q = cfg.base, cfg.quote
    buy, sell = (q.mint, b.mint, q.atoms(size)), (b.mint, q.mint, b.atoms(size))
    control = jupiter(SOL, CASH, 10**7, side="control")  # 0.01 SOL: tells an API failure from an unrouted market
    quotes = [
        world(*buy, side="buy"),
        world(*sell, side="sell"),
        jupiter(*buy, side="buy"),
        jupiter(*sell, side="sell"),
        control,
    ]

    def price(r: Route) -> Decimal | None:
        if r.side == "control" or not r.out_atoms:
            return None
        cash, token = (r.in_atoms, r.out_atoms) if r.side == "buy" else (r.out_atoms, r.in_atoms)
        return (Decimal(cash) / token * Decimal(10) ** (b.decimals - q.decimals)).quantize(Decimal("0.0001"))

    def gets(r: Route) -> str | None:
        out = {"buy": b, "sell": q}.get(r.side)
        return f"{out.ui(r.out_atoms)} {out.symbol}" if out and r.out_atoms else None

    def row(r: Route) -> dict:
        venues = ", ".join(leg.venue for leg in r.legs) or None
        return {
            "router": r.router,
            "side": r.side,
            "venues": venues,
            "yours": r.yours(cfg.market),
            "gets": gets(r),
            "price": price(r),
            "error": r.error,
        }

    return [row(r) for r in quotes]
