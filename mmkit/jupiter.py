"""SOL <-> CASH through Jupiter's keyless swap API."""

import base64
from urllib.parse import urlencode

from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction

from mmkit.web import get_json, post_json

API = "https://lite-api.jup.ag/swap/v1"
SOL = Pubkey.from_string("So11111111111111111111111111111111111111112")


def quote(input_mint: Pubkey, output_mint: Pubkey, atoms: int, slippage_bps: int = 50) -> dict:
    q = get_json(
        f"{API}/quote?"
        + urlencode(
            {"inputMint": str(input_mint), "outputMint": str(output_mint), "amount": atoms, "slippageBps": slippage_bps}
        )
    )
    if "outAmount" not in q:
        raise SystemExit(f"Jupiter has no route: {q.get('error', q)}")
    return q


def swap_tx(q: dict, owner: Pubkey) -> VersionedTransaction:
    """Unsigned transaction for the quote, built by Jupiter."""
    s = post_json(f"{API}/swap", {"quoteResponse": q, "userPublicKey": str(owner), "dynamicComputeUnitLimit": True})
    return VersionedTransaction.from_bytes(base64.b64decode(s["swapTransaction"]))
