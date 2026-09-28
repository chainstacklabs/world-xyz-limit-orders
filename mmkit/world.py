"""World's prediction markets: find them, read them, price them, turn one into market.json."""

import base64
import json
import os
import struct
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

from solders.pubkey import Pubkey

from mmkit import rpc
from mmkit.web import get_json

PROGRAM = Pubkey.from_string("prediCtPZCttYMvm2W3PtxmMxLmT1dtN7riU6Cxh6tM")
CASH = Pubkey.from_string("CASHx9KJUStyftLFWGvEVf59SGeG9sh5FfcnZMVPCASH")
MARKET_SIZE = 320
MARKET_DISC = bytes.fromhex("dbbed53700e3c69a")
ROUTER = "https://aggregator-api-proxy.world-xyz.workers.dev/order"
ONE = 10**6  # 1 CASH or 1 outcome token; World mints use 6 decimals
ROUTER_HEADERS = {"origin": "https://world.xyz", "referer": "https://world.xyz/"}


@dataclass(frozen=True)
class Market:
    address: Pubkey
    cash_mint: Pubkey
    yes_mint: Pubkey
    no_mint: Pubkey
    vault: Pubkey
    start: datetime | None  # trading window; long-dated markets have none
    end: datetime | None
    resolved: bool = False

    def ended(self) -> bool:
        return self.end is not None and self.end < datetime.now(UTC)

    def status(self) -> str:
        """upcoming, live, ended (awaiting resolution), resolved, or open (long-dated)."""
        now = datetime.now(UTC)
        if self.resolved:
            return "resolved"
        if self.end is None:
            return "open"
        return "upcoming" if now < self.start else "live" if now <= self.end else "ended"


def parse_market(address: Pubkey, data: bytes) -> Market:
    if data[:8] != MARKET_DISC:
        raise SystemExit(f"{address} is not a World market")
    pk = lambda at: Pubkey.from_bytes(data[at : at + 32])
    start, end = struct.unpack_from("<QQ", data, 258)  # milliseconds; zero, or another layout, when there is no window
    window = 1.6e12 < start < end < 2.2e12
    ts = lambda ms: datetime.fromtimestamp(ms / 1000, UTC) if window else None
    resolved = data[283] == 1  # Option tag of the resolution value; set by determine_outcome (checked 2026-09-28)
    return Market(address, pk(40), pk(72), pk(104), pk(136), ts(start), ts(end), resolved)


def list_markets() -> list[Market]:
    opts = {"encoding": "base64", "filters": [{"dataSize": MARKET_SIZE}]}
    accs = (
        (Pubkey.from_string(a["pubkey"]), base64.b64decode(a["account"]["data"][0]))
        for a in rpc.call("getProgramAccounts", [str(PROGRAM), opts])
    )
    return [parse_market(key, data) for key, data in accs if data[:8] == MARKET_DISC]


def metadata(mints: list[Pubkey]) -> dict[Pubkey, dict]:
    """Token-2022 metadata (symbol, name, uri) per live mint; closed mints are absent."""
    out = {}
    for i in range(0, len(mints), 100):
        batch = mints[i : i + 100]
        for mint, acc in zip(
            batch, rpc.call("getMultipleAccounts", [[str(m) for m in batch], {"encoding": "jsonParsed"}])["value"]
        ):
            info = (acc or {}).get("data", {}).get("parsed", {}).get("info", {})
            md = next((e["state"] for e in info.get("extensions") or [] if e["extension"] == "tokenMetadata"), None)
            if md:
                out[mint] = {
                    "symbol": md["symbol"],
                    "name": md["name"],
                    "uri": md["uri"],
                    "decimals": info["decimals"],
                    "program": acc["owner"],
                }
    return out


def description(uri: str) -> str | None:
    try:
        return get_json(uri).get("description")
    except (SystemExit, OSError, ValueError):
        return None


def _cache() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "mm" / "questions.json"


def questions(uris: dict[Pubkey, str]) -> dict[Pubkey, str | None]:
    """Each market's question, from its metadata JSON; cached forever, since it never changes."""
    path = _cache()
    cache = json.loads(path.read_text()) if path.exists() else {}
    missing = [m for m in uris if str(m) not in cache]
    with ThreadPoolExecutor(16) as pool:
        for mint, q in zip(missing, pool.map(lambda m: description(uris[m]), missing)):
            if q:
                cache[str(mint)] = q
    if missing:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache))
    return {m: cache.get(str(m)) for m in uris}


def matches(row: dict, text: str) -> bool:
    return any(text.lower() in (row.get(k) or "").lower() for k in ("ticker", "name", "question"))


def router_quote(input_mint: Pubkey, output_mint: Pubkey, atoms: int) -> int | None:
    """Output atoms World's router would give for `atoms` of input; None if it has no route."""
    q = urlencode({"inputMint": str(input_mint), "outputMint": str(output_mint), "amount": atoms, "slippageBps": 100})
    try:
        out = get_json(f"{ROUTER}?{q}", ROUTER_HEADERS).get("outAmount")
    except (SystemExit, OSError, ValueError):
        return None
    return int(out) if out else None


def buy_price(m: Market, mint: Pubkey) -> Decimal | None:
    """CASH per token when buying 1 CASH worth through World's router; None without a quote."""
    out = router_quote(m.cash_mint, mint, ONE)
    return (Decimal(ONE) / out).quantize(Decimal("0.0001")) if out else None


def sell_price(m: Market, mint: Pubkey) -> Decimal | None:
    """CASH received for 1 token through World's router; None without a quote."""
    out = router_quote(mint, m.cash_mint, ONE)
    return Decimal(out) / ONE if out else None


def to_config(m: Market, side: str = "yes", quote=None) -> dict:
    """market.json for this market: `side` picks the traded outcome token, `quote` the book's currency (default CASH)."""
    md = metadata([m.yes_mint, m.no_mint, m.cash_mint])
    if m.yes_mint not in md or m.no_mint not in md:
        raise SystemExit(f"{m.address} is closed — its outcome mints no longer exist")
    token = lambda mint: {
        "symbol": md[mint]["symbol"],
        "mint": str(mint),
        "decimals": md[mint]["decimals"],
        "tokenProgram": md[mint]["program"],
    }
    base, other = (token(m.yes_mint), token(m.no_mint)) if side == "yes" else (token(m.no_mint), token(m.yes_mint))
    cash = token(m.cash_mint)
    q = (
        cash
        if quote is None
        else {
            "symbol": quote.symbol,
            "mint": str(quote.mint),
            "decimals": quote.decimals,
            "tokenProgram": str(quote.program),
        }
    )
    return {
        "name": f"{base['symbol']} / {q['symbol']}",
        "base": base,
        "quote": q,
        "counterpart": other,
        "collateral": cash,
        "issuer": {"program": str(PROGRAM), "ledger": str(m.address), "collateralVault": str(m.vault)},
        "venue": {"kind": "manifest", "market": None, "side": side},
    }
