"""Minimal Solana JSON-RPC client. Never prints the endpoint."""

import base64
import json
import time
import urllib.request
from dataclasses import dataclass

from solders.hash import Hash
from solders.pubkey import Pubkey

from mmkit.config import rpc_url


class RpcError(SystemExit):
    """One line on stderr and exit 1, from `mm` or a standalone command."""

    def __init__(self, message: str):
        super().__init__(f"RPC error — {message}")


@dataclass(frozen=True)
class Account:
    data: bytes
    lamports: int
    owner: Pubkey
    executable: bool


def call(method: str, params: list):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(rpc_url(), data=body, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.loads(r.read())
    except OSError as e:
        raise RpcError(f"cannot reach RPC_URL: {getattr(e, 'reason', e)}") from None
    except ValueError:
        raise RpcError(f"{method}: not a JSON-RPC response") from None
    if "error" in out:
        raise RpcError(f"{method}: {out['error'].get('message', out['error'])}")
    return out["result"]


def account(pubkey: Pubkey) -> Account | None:
    v = call("getAccountInfo", [str(pubkey), {"encoding": "base64", "commitment": "confirmed"}])["value"]
    if v is None:
        return None
    return Account(base64.b64decode(v["data"][0]), v["lamports"], Pubkey.from_string(v["owner"]), v["executable"])


def balance(pubkey: Pubkey) -> int:
    return call("getBalance", [str(pubkey), {"commitment": "confirmed"}])["value"]


def token_balance(token_account: Pubkey) -> int:
    a = account(token_account)
    return 0 if a is None else int.from_bytes(a.data[64:72], "little")  # amount: after mint(32) + owner(32)


def blockhash() -> Hash:
    return Hash.from_string(call("getLatestBlockhash", [{"commitment": "confirmed"}])["value"]["blockhash"])


def rent(size: int) -> int:
    return call("getMinimumBalanceForRentExemption", [size])


def slot() -> int:
    return call("getSlot", [{"commitment": "confirmed"}])


def confirm(sig: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        s = call("getSignatureStatuses", [[sig]])["value"][0]
        if s and s.get("err"):
            raise RpcError(f"transaction failed: {s['err']}")
        if s and s.get("confirmationStatus") in ("confirmed", "finalized"):
            return
        time.sleep(1)
    raise RpcError(f"not confirmed after {timeout:.0f}s: {sig}")
