"""Program ids and wallet token accounts."""

from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey

from mmkit.config import Token

SYSTEM_PROGRAM = Pubkey.from_string("11111111111111111111111111111111")
TOKEN_PROGRAM = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
TOKEN_2022_PROGRAM = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
ATA_PROGRAM = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")


def ata(owner: Pubkey, token: Token) -> Pubkey:
    return Pubkey.find_program_address([bytes(owner), bytes(token.program), bytes(token.mint)], ATA_PROGRAM)[0]


def create_ata(payer: Pubkey, token: Token) -> Instruction:
    """Create the payer's token account if missing; no-op if it exists."""
    keys = [
        AccountMeta(payer, True, True),
        AccountMeta(ata(payer, token), False, True),
        AccountMeta(payer, False, False),
        AccountMeta(token.mint, False, False),
        AccountMeta(SYSTEM_PROGRAM, False, False),
        AccountMeta(token.program, False, False),
    ]
    return Instruction(ATA_PROGRAM, bytes([1]), keys)


def close_account(owner: Pubkey, token: Token) -> Instruction:
    """Close the owner's empty token account; its rent goes back to the owner."""
    keys = [
        AccountMeta(ata(owner, token), False, True),
        AccountMeta(owner, False, True),
        AccountMeta(owner, True, False),
    ]
    return Instruction(token.program, bytes([9]), keys)  # CloseAccount


def close_empty(owner: Pubkey, accounts: list[tuple[Token, int | None]]) -> list[Instruction]:
    """Close each account whose balance is 0; None means the account doesn't exist."""
    return [close_account(owner, t) for t, balance in accounts if balance == 0]
