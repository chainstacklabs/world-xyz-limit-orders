"""Ask before anything is sent."""

import sys
from urllib.parse import urlparse

from mmkit.config import rpc_url

LOCAL_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0"}


def is_local(url: str) -> bool:
    return urlparse(url).hostname in LOCAL_HOSTS


def confirm(yes: bool) -> None:
    """After a clean simulation: `--yes` sends; otherwise ask, and a caller with no terminal must pass --yes."""
    if yes:
        return
    if not sys.stdin.isatty():
        raise SystemExit("not sent — no terminal to ask; add --yes to send")
    where = "the local RPC" if is_local(rpc_url()) else "mainnet (real funds)"
    if input(f"send on {where}? [y/N] ").strip().lower() not in ("y", "yes"):
        raise SystemExit("not sent")


def fork_only(url: str) -> None:
    if not is_local(url):
        raise SystemExit("fork only — RPC_URL must point at a local fork")
