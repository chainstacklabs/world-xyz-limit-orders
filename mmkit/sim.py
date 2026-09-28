"""Simulate every transaction; send only when asked."""

import base64
import time
from decimal import Decimal

from solders.instruction import Instruction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction, VersionedTransaction

from mmkit import fork, rpc
from mmkit.config import rpc_url
from mmkit.guards import confirm, is_local


def simulate_or_send(
    ixs: list[Instruction],
    payer: Keypair,
    send: bool,
    signers: tuple[Keypair, ...] = (),
    rent_of: tuple[Pubkey, ...] = (),
    yes: bool = False,
) -> str | None:
    """rent_of: accounts whose lamports after the transaction are reported as locked rent."""
    tx = Transaction.new_signed_with_payer(ixs, payer.pubkey(), [payer, *signers], rpc.blockhash())
    _on_fork(tx.message)
    return _run(bytes(tx), send, rent_of, yes)


def sign_and_run(tx: VersionedTransaction, payer: Keypair, send: bool, yes: bool = False) -> str | None:
    """For transactions built elsewhere (Jupiter): sign, then the same simulate-first path."""
    _on_fork(tx.message)
    return _run(bytes(VersionedTransaction(tx.message, [payer])), send, yes=yes)


def _on_fork(message) -> None:
    if is_local(rpc_url()) and (n := fork.top_up(fork.writable(message))):
        print(f"fork: topped up {n} account(s) to the fork's rent rate")


def _run(tx: bytes, send: bool, rent_of: tuple[Pubkey, ...] = (), yes: bool = False) -> str | None:
    raw = base64.b64encode(tx).decode()
    opts = {"encoding": "base64", "commitment": "confirmed"}
    if rent_of:
        opts["accounts"] = {"encoding": "base64", "addresses": [str(k) for k in rent_of]}
    for _ in range(3):  # a load-balanced RPC may simulate on a node that hasn't seen the blockhash yet
        sim = rpc.call("simulateTransaction", [raw, opts])["value"]
        if sim["err"] != "BlockhashNotFound":
            break
        time.sleep(1)
    if sim["err"]:
        print(f"simulation failed: {sim['err']}")
        for line in (sim.get("logs") or [])[-10:]:
            print(f"  {line}")
        raise SystemExit(1)
    print(f"simulation ok ({sim['unitsConsumed']} CU)")
    if rent_of:
        sol = Decimal(sum(a["lamports"] for a in sim["accounts"] if a)) / 10**9
        print(f"rent locked for good: {format(sol.normalize(), 'f')} SOL")
    if not send:
        print("dry run — pass --send to execute")
        return None
    confirm(yes)
    sig = rpc.call("sendTransaction", [raw, {"encoding": "base64", "preflightCommitment": "confirmed"}])
    print(f"sent {sig}")
    try:
        rpc.confirm(sig)
    except rpc.RpcError as e:
        raise SystemExit(f"{e} — it may still land; check `mm orders` or `mm wallet` before retrying") from None
    print("confirmed")
    return sig
