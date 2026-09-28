"""World's issuer: mint and redeem complete sets, 1 CASH <-> 1 YES + 1 NO, whichever side is traded."""

import hashlib
import struct

from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey

from mmkit.config import Config
from mmkit.spl import ata, close_empty


def _ix(name: str, cfg: Config, owner: Pubkey, atoms: int) -> Instruction:
    w = lambda p, signer=False: AccountMeta(p, signer, True)
    r = lambda p: AccountMeta(p, False, False)
    keys = [
        w(owner, True),
        w(cfg.issuer.ledger),
        w(cfg.collateral.mint),
        w(cfg.yes.mint),
        w(cfg.no.mint),
        w(ata(owner, cfg.collateral)),
        w(cfg.issuer.collateral_vault),
        w(ata(owner, cfg.yes)),
        w(ata(owner, cfg.no)),
        r(cfg.collateral.program),
        r(cfg.yes.program),
    ]
    disc = hashlib.sha256(f"global:{name}".encode()).digest()[:8]  # Anchor discriminator
    return Instruction(cfg.issuer.program, disc + struct.pack("<Q", atoms), keys)


def split(cfg: Config, owner: Pubkey, atoms: int) -> Instruction:
    return _ix("split", cfg, owner, atoms)


def merge(cfg: Config, owner: Pubkey, atoms: int) -> Instruction:
    return _ix("merge", cfg, owner, atoms)


def merge_ixs(cfg: Config, owner: Pubkey, atoms: int, base_balance: int, counterpart_balance: int) -> list[Instruction]:
    """Merge, then close the base and counterpart accounts the merge empties."""
    left = [(cfg.base, base_balance - atoms), (cfg.counterpart, counterpart_balance - atoms)]
    return [merge(cfg, owner, atoms), *close_empty(owner, left)]
