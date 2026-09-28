"""Point market.json at a World market."""

from enum import Enum
from typing import Annotated

import typer
from solders.pubkey import Pubkey

from mmkit import books, config, rpc, world
from mmkit.common import Json, emit_one
from mmkit.venue import manifest

Force = Annotated[bool, typer.Option("--force", help="Replace a market.json that points at another market.")]
Quote = Annotated[str | None, typer.Option("--quote", help="Mint of the book's quote currency; default CASH.")]


class Outcome(str, Enum):
    yes = "yes"
    no = "no"


def main(
    address: str, side: Outcome = Outcome.yes, quote: Quote = None, force: Force = False, as_json: Json = False
) -> None:
    """Write market.json for a World market and one of its outcome tokens; picks its Manifest book when there is exactly one."""
    old = config.existing()
    if old and old["issuer"]["ledger"] != address and not force:
        raise SystemExit(f"market.json points at {old['name']} — pass --force to replace it")
    acc = rpc.account(Pubkey.from_string(address))
    if acc is None:
        raise SystemExit(f"{address} not found — closed, or not a market address")
    m = world.parse_market(Pubkey.from_string(address), acc.data)
    d = world.to_config(m, side.value, books.token(quote) if quote else None)
    pair = (Pubkey.from_string(d["base"]["mint"]), Pubkey.from_string(d["quote"]["mint"]))
    found = [str(k) for k in manifest.find_markets(*pair)]
    d["venue"]["market"] = config.chosen_book(old, d, found)
    config.save(d)
    out = {"name": d["name"], "side": side.value, "manifest_market": d["venue"]["market"], "manifest_markets": found}
    if not d["venue"]["market"] and not as_json:
        out["next"] = "set venue.market to one of these, or run `mm create`"
    emit_one(out, as_json, "wrote market.json")


if __name__ == "__main__":
    typer.run(main)
