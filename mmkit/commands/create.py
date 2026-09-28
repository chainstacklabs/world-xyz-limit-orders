"""Create a Manifest market for the configured pair."""

import typer
from solders.keypair import Keypair
from solders.system_program import CreateAccountParams, create_account

from mmkit import rpc
from mmkit.common import Send, Yes
from mmkit.config import load, save_market, wallet
from mmkit.sim import simulate_or_send
from mmkit.venue import manifest


def main(send: Send = False, yes: Yes = False) -> None:
    """Create a Manifest market and write it to market.json. Its rent is locked for good."""
    cfg, me = load(), wallet()
    if cfg.market:
        raise SystemExit(f"market.json already points at {cfg.market} — clear venue.market to create another")
    market = Keypair()
    lamports = rpc.rent(manifest.HEADER)
    params = CreateAccountParams(
        from_pubkey=me.pubkey(),
        to_pubkey=market.pubkey(),
        lamports=lamports,
        space=manifest.HEADER,
        owner=manifest.PROGRAM,
    )
    ixs = [
        create_account(params),
        manifest.create_market(me.pubkey(), market.pubkey(), cfg.base, cfg.quote),
        manifest.expand(me.pubkey(), market.pubkey()),
    ]
    print(f"new market {market.pubkey()}  {cfg.base.symbol}/{cfg.quote.symbol}")
    rent_of = (
        market.pubkey(),
        manifest.vault(market.pubkey(), cfg.base.mint),
        manifest.vault(market.pubkey(), cfg.quote.mint),
    )
    if simulate_or_send(ixs, me, send, yes=yes, signers=(market,), rent_of=rent_of):
        save_market(market.pubkey())
        print("saved to market.json")


if __name__ == "__main__":
    typer.run(main)
