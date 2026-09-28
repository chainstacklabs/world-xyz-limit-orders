"""market.json + environment. The only place addresses are read from."""

import json
import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from solders.keypair import Keypair
from solders.pubkey import Pubkey

MARKET_FILE = Path(os.environ.get("MARKET_FILE", "market.json"))


@dataclass(frozen=True)
class Token:
    symbol: str
    mint: Pubkey
    decimals: int
    program: Pubkey

    def atoms(self, amount: str | Decimal) -> int:
        try:
            scaled = Decimal(amount) * 10**self.decimals
        except InvalidOperation:
            scaled = Decimal("NaN")
        if not scaled.is_finite() or scaled < 0 or scaled != scaled.to_integral_value():
            raise SystemExit(f"{amount} is not a valid {self.symbol} amount ({self.decimals} decimals)")
        return int(scaled)

    def ui(self, atoms: int) -> Decimal:
        return Decimal(atoms) / 10**self.decimals


@dataclass(frozen=True)
class Issuer:
    program: Pubkey
    ledger: Pubkey
    collateral_vault: Pubkey


@dataclass(frozen=True)
class Config:
    name: str
    base: Token
    quote: Token
    counterpart: Token
    issuer: Issuer
    market: Pubkey | None
    side: str = "yes"  # which outcome token is traded: base is YES, or base is NO
    collateral_token: Token | None = None  # World's collateral when the book is quoted in something else

    @property
    def collateral(self) -> Token:
        return self.collateral_token or self.quote

    @property
    def yes(self) -> Token:
        return self.base if self.side == "yes" else self.counterpart

    @property
    def no(self) -> Token:
        return self.counterpart if self.side == "yes" else self.base


def _token(d: dict) -> Token:
    return Token(d["symbol"], Pubkey.from_string(d["mint"]), d["decimals"], Pubkey.from_string(d["tokenProgram"]))


def load(path: Path = MARKET_FILE) -> Config:
    if not path.exists():
        raise SystemExit(f"{path} not found — run `mm markets`, then `mm use <market>`")
    d = json.loads(path.read_text())
    i = d["issuer"]
    return Config(
        name=d["name"],
        base=_token(d["base"]),
        quote=_token(d["quote"]),
        counterpart=_token(d["counterpart"]),
        issuer=Issuer(*(Pubkey.from_string(i[k]) for k in ("program", "ledger", "collateralVault"))),
        market=Pubkey.from_string(d["venue"]["market"]) if d["venue"].get("market") else None,
        side=d["venue"].get("side", "yes"),
        collateral_token=_token(d["collateral"]) if "collateral" in d else None,
    )


def require_market(cfg: Config) -> Pubkey:
    if cfg.market is None:
        raise SystemExit("venue.market is empty — run `mm create`, or set it to an existing Manifest market")
    return cfg.market


def existing(path: Path = MARKET_FILE) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def chosen_book(old: dict | None, new: dict, found: list[str]) -> str | None:
    """Keep a book already set for the same market, side and quote; otherwise the only one found."""
    same = (
        old
        and old["issuer"]["ledger"] == new["issuer"]["ledger"]
        and old["venue"].get("side", "yes") == new["venue"]["side"]
        and old["quote"]["mint"] == new["quote"]["mint"]
    )
    return (same and old["venue"].get("market")) or (found[0] if len(found) == 1 else None)


def save(d: dict, path: Path = MARKET_FILE) -> None:
    path.write_text(json.dumps(d, indent=2) + "\n")


def save_market(market: Pubkey, path: Path = MARKET_FILE) -> None:
    d = json.loads(path.read_text())
    d["venue"]["market"] = str(market)
    save(d, path)


def rpc_url() -> str:
    url = os.environ.get("RPC_URL")
    if not url:
        raise SystemExit("RPC_URL is not set — see .env.example")
    return url


def wallet() -> Keypair:
    path = os.environ.get("WALLET_KEY")
    if not path:
        raise SystemExit("WALLET_KEY is not set — see .env.example")
    try:
        return Keypair.from_json(Path(path).expanduser().read_text())
    except (OSError, ValueError):
        raise SystemExit(f"WALLET_KEY {path} is not a readable keypair file") from None
