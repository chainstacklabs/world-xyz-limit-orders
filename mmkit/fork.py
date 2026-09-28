"""Practice on a local surfpool fork of mainnet."""

from solders.pubkey import Pubkey

from mmkit import rpc, world
from mmkit.spl import TOKEN_2022_PROGRAM

FORK_URL = "http://127.0.0.1:8999"


def surfpool_args(source_url: str) -> list[str]:
    """Fork from the given RPC — never surfpool's --network shortcut, which uses a public endpoint."""
    return [
        "surfpool",
        "start",
        "--rpc-url",
        source_url,
        "--no-tui",
        "--no-studio",
        "--no-deploy",
        "-y",
        "--port",
        "8999",
        "--ws-port",
        "9000",
    ]


def fund(owner: Pubkey, lamports: int | None, cash_atoms: int | None) -> None:
    """Set the wallet's SOL and CASH on the fork."""
    if lamports is not None:
        rpc.call("surfnet_setAccount", [str(owner), {"lamports": lamports}])
    if cash_atoms is not None:
        rpc.call(
            "surfnet_setTokenAccount", [str(owner), str(world.CASH), {"amount": cash_atoms}, str(TOKEN_2022_PROGRAM)]
        )


def top_up(keys: list[Pubkey]) -> int:
    """Raise accounts cloned from mainnet to the fork's rent minimum; surfpool charges more per byte
    (6,960 vs 5,080 lamports, 2026-09-28), so growing a cloned account otherwise fails with
    InsufficientFundsForRent. Returns how many were topped up; 0 on a local RPC without cheatcodes."""
    count = 0
    for key in keys:
        acc = rpc.account(key)
        if acc is None:
            continue
        need = rpc.rent(len(acc.data))
        if acc.lamports < need:
            try:
                rpc.call("surfnet_setAccount", [str(key), {"lamports": need}])
            except rpc.RpcError:
                return count
            count += 1
    return count


def writable(message) -> list[Pubkey]:
    """Writable accounts of a legacy or v0 message, from its header (lookup-table accounts not included)."""
    h, keys = message.header, list(message.account_keys)
    signed, n = h.num_required_signatures, len(keys)
    return [
        k
        for i, k in enumerate(keys)
        if (i < signed - h.num_readonly_signed_accounts) or (signed <= i < n - h.num_readonly_unsigned_accounts)
    ]
