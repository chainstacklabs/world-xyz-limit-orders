"""Manifest order book, core program only: read a market account, build instructions."""

import base64
import math
import re
import struct
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey

from mmkit import rpc
from mmkit.config import Token
from mmkit.spl import SYSTEM_PROGRAM, TOKEN_2022_PROGRAM, TOKEN_PROGRAM, ata, create_ata

PROGRAM = Pubkey.from_string("MNFSTqtC93rEfYHB6hF82sKdZpUDFWkViLByLd1k1Ms")
HEADER = 256
NIL = 0xFFFFFFFF
NODE = 16  # red-black tree node header: left, right, parent (u32), colour (u8) + padding
FILL_LOG = bytes.fromhex("3ae6f2034b7104a9")  # keccak256(program id + "manifest::logs::FillLog")[:8]


@dataclass(frozen=True)
class Order:
    seq: int
    trader: Pubkey
    is_bid: bool
    base_atoms: int
    price: Decimal  # quote tokens per base token
    price_d18: int  # the program's price: quote atoms per base atom, x 1e18

    def locked_quote(self, round_up: bool = False) -> int:
        """Quote atoms a bid of this size holds, exactly."""
        q, r = divmod(self.base_atoms * self.price_d18, 10**18)
        return q + (1 if round_up and r else 0)


@dataclass(frozen=True)
class Seat:
    trader: Pubkey
    base_atoms: int
    quote_atoms: int


@dataclass(frozen=True)
class Market:
    base_mint: Pubkey
    quote_mint: Pubkey
    base_decimals: int
    quote_decimals: int
    size: int
    has_free_block: bool
    bids: list[Order]  # best first
    asks: list[Order]  # best first
    seats: list[Seat]

    def seat(self, trader: Pubkey) -> Seat | None:
        return next((s for s in self.seats if s.trader == trader), None)

    def mine(self, trader: Pubkey, is_bid: bool) -> list[Order]:
        return [o for o in (self.bids if is_bid else self.asks) if o.trader == trader]


def _walk(data: bytes, root: int) -> list[int]:
    """In-order walk of one tree; returns payload offsets."""
    out, stack, i = [], [], root
    while stack or i != NIL:
        while i != NIL:
            stack.append(i)
            i = struct.unpack_from("<I", data, HEADER + i)[0]
        i = stack.pop()
        out.append(HEADER + i + NODE)
        i = struct.unpack_from("<I", data, HEADER + i + 4)[0]
    return out


def parse(data: bytes, slot: int = 0) -> Market:
    base_dec, quote_dec = data[9], data[10]
    bids_root, _, asks_root, _, seats_root, free = struct.unpack_from("<6I", data, 156)
    scale = Decimal(10) ** (base_dec - quote_dec) / Decimal(10) ** 18  # price is quote atoms per base atom, x 1e18

    def order(off: int) -> Order | None:
        lo, hi, atoms, seq, trader_at, last_valid_slot, is_bid = struct.unpack_from("<QQQQII?", data, off)
        if last_valid_slot and last_valid_slot < slot:  # the program's is_expired
            return None
        trader = Pubkey.from_bytes(data[HEADER + trader_at + NODE : HEADER + trader_at + NODE + 32])
        d18 = lo + (hi << 64)
        return Order(seq, trader, is_bid, atoms, Decimal(d18) * scale, d18)

    def orders(root: int) -> list[Order]:
        return [o for o in map(order, _walk(data, root)) if o]

    def seat(off: int) -> Seat:
        return Seat(Pubkey.from_bytes(data[off : off + 32]), *struct.unpack_from("<QQ", data, off + 32))

    return Market(
        base_mint=Pubkey.from_bytes(data[16:48]),
        quote_mint=Pubkey.from_bytes(data[48:80]),
        base_decimals=base_dec,
        quote_decimals=quote_dec,
        size=len(data),
        has_free_block=free != NIL,
        bids=sorted(orders(bids_root), key=lambda o: (-o.price, o.seq)),
        asks=sorted(orders(asks_root), key=lambda o: (o.price, o.seq)),
        seats=[seat(off) for off in _walk(data, seats_root)],
    )


def vault(market: Pubkey, mint: Pubkey) -> Pubkey:
    return Pubkey.find_program_address([b"vault", bytes(market), bytes(mint)], PROGRAM)[0]


def find_markets(base_mint: Pubkey, quote_mint: Pubkey) -> list[Pubkey]:
    """Every Manifest market for this pair."""
    filters = [
        {"memcmp": {"offset": 16, "bytes": str(base_mint)}},
        {"memcmp": {"offset": 48, "bytes": str(quote_mint)}},
    ]
    accs = rpc.call(
        "getProgramAccounts",
        [str(PROGRAM), {"encoding": "base64", "dataSlice": {"offset": 0, "length": 0}, "filters": filters}],
    )
    return [Pubkey.from_string(a["pubkey"]) for a in accs]


@dataclass(frozen=True)
class Fill:
    signature: str
    time: datetime
    market: Pubkey
    maker: Pubkey
    taker: Pubkey
    base_atoms: int
    quote_atoms: int
    price: Decimal
    maker_seq: int
    taker_is_buy: bool


def parse_fills(logs: list[str], base_decimals: int, quote_decimals: int, signature: str, time: datetime) -> list[Fill]:
    """FillLog events from a transaction's logs."""
    scale = Decimal(10) ** (base_decimals - quote_decimals) / Decimal(10) ** 18
    out, running = [], []  # program call stack: only data Manifest itself logged counts
    for line in logs:
        if call := re.fullmatch(r"Program (\w+) invoke \[\d+\]", line):
            running.append(call[1])
            continue
        if re.fullmatch(r"Program \w+ (success|failed.*)", line) and running:
            running.pop()
            continue
        if not line.startswith("Program data: ") or not running or running[-1] != str(PROGRAM):
            continue
        b = base64.b64decode(line[14:])
        if b[:8] != FILL_LOG:
            continue
        market, maker, taker = (Pubkey.from_bytes(b[at : at + 32]) for at in (8, 40, 72))
        lo, hi, base_atoms, quote_atoms, maker_seq, _, taker_is_buy = struct.unpack_from("<QQQQQQ?", b, 168)
        out.append(
            Fill(
                signature,
                time,
                market,
                maker,
                taker,
                base_atoms,
                quote_atoms,
                Decimal(lo + (hi << 64)) * scale,
                maker_seq,
                taker_is_buy,
            )
        )
    return out


@dataclass(frozen=True)
class Place:
    is_bid: bool
    base_atoms: int
    mantissa: int
    exponent: int

    def quote_atoms(self) -> int:
        return math.ceil(self.base_atoms * self.mantissa * Decimal(10) ** self.exponent)


def order(is_bid: bool, base_atoms: int, price: Decimal, base: Token, quote: Token) -> Place:
    """Price in quote tokens per base token -> the program's u32 mantissa and exponent.
    Bids round down and asks up, so the order is never worse than the price asked for."""
    atom_price = Decimal(price) * Decimal(10) ** (quote.decimals - base.decimals)
    if atom_price <= 0 or base_atoms <= 0:
        raise SystemExit("size and price must be positive")
    rounding = ROUND_FLOOR if is_bid else ROUND_CEILING
    for exp in range(-18, 9):  # the program's exponent range
        mantissa = int((atom_price / Decimal(10) ** exp).to_integral_value(rounding))
        if mantissa == 0:
            raise SystemExit(f"price {price} is too small for this market")
        if mantissa < 2**32:
            return Place(is_bid, base_atoms, mantissa, exp)
    raise SystemExit(f"price {price} is too large")


def crosses(m: Market, is_bid: bool, price: Decimal) -> bool:
    """Would an order at this price fill at once against the book?"""
    if is_bid:
        return bool(m.asks) and price >= m.asks[0].price
    return bool(m.bids) and price <= m.bids[0].price


def _keys(*metas: tuple[Pubkey, bool, bool]) -> list[AccountMeta]:
    return [AccountMeta(p, signer, writable) for p, signer, writable in metas]


def create_market(payer: Pubkey, market: Pubkey, base: Token, quote: Token) -> Instruction:
    keys = _keys(
        (payer, True, True),
        (market, False, True),
        (SYSTEM_PROGRAM, False, False),
        (base.mint, False, False),
        (quote.mint, False, False),
        (vault(market, base.mint), False, True),
        (vault(market, quote.mint), False, True),
        (TOKEN_PROGRAM, False, False),
        (TOKEN_2022_PROGRAM, False, False),
    )
    return Instruction(PROGRAM, bytes([0]), keys)


def swap(
    payer: Pubkey, market: Pubkey, base: Token, quote: Token, in_atoms: int, min_out: int, is_base_in: bool
) -> Instruction:
    """A taker's exact-in swap against the book; only ever simulated here."""
    keys = [
        (payer, True, True),
        (market, False, True),
        (SYSTEM_PROGRAM, False, False),
        (ata(payer, base), False, True),
        (ata(payer, quote), False, True),
        (vault(market, base.mint), False, True),
        (vault(market, quote.mint), False, True),
        (base.program, False, False),
        (base.mint, False, False),
    ]
    if quote.program != base.program:
        keys.append((quote.program, False, False))
    keys.append((quote.mint, False, False))  # optional accounts: the program tells them apart by owner
    return Instruction(PROGRAM, bytes([4]) + struct.pack("<QQ??", in_atoms, min_out, is_base_in, True), _keys(*keys))


def claim_seat(payer: Pubkey, market: Pubkey) -> Instruction:
    return Instruction(
        PROGRAM, bytes([1]), _keys((payer, True, True), (market, False, True), (SYSTEM_PROGRAM, False, False))
    )


def _move(disc: int, payer: Pubkey, market: Pubkey, token: Token, atoms: int) -> Instruction:
    keys = _keys(
        (payer, True, True),
        (market, False, True),
        (ata(payer, token), False, True),
        (vault(market, token.mint), False, True),
        (token.program, False, False),
        (token.mint, False, False),
    )
    return Instruction(PROGRAM, bytes([disc]) + struct.pack("<Q", atoms) + b"\x00", keys)  # trader_index_hint: None


def deposit(payer: Pubkey, market: Pubkey, token: Token, atoms: int) -> Instruction:
    return _move(2, payer, market, token, atoms)


def withdraw(payer: Pubkey, market: Pubkey, token: Token, atoms: int) -> Instruction:
    return _move(3, payer, market, token, atoms)


def expand(payer: Pubkey, market: Pubkey) -> Instruction:
    """Adds one spare block; does nothing if one exists. Keeps fills from spending taker SOL."""
    return Instruction(
        PROGRAM, bytes([5]), _keys((payer, True, True), (market, False, True), (SYSTEM_PROGRAM, False, False))
    )


def batch(payer: Pubkey, market: Pubkey, cancels: list[int], places: list[Place]) -> Instruction:
    """Cancels (by order sequence number) run before places, so a reprice is atomic."""
    data = bytes([6, 0])  # discriminator, trader_index_hint: None
    data += struct.pack("<I", len(cancels)) + b"".join(struct.pack("<Q", s) + b"\x00" for s in cancels)
    data += struct.pack("<I", len(places)) + b"".join(
        struct.pack("<QIb?IB", p.base_atoms, p.mantissa, p.exponent, p.is_bid, 0, 0)
        for p in places  # no expiry, Limit
    )
    return Instruction(PROGRAM, data, _keys((payer, True, True), (market, False, True), (SYSTEM_PROGRAM, False, False)))


def place_ixs(m: Market, market: Pubkey, owner: Pubkey, base: Token, quote: Token, p: Place) -> list[Instruction]:
    """Claim a seat if needed, deposit only what the seat lacks, rest the order, keep a spare block."""
    seat = m.seat(owner)
    ixs = [] if seat else [claim_seat(owner, market)]
    have = 0 if seat is None else seat.quote_atoms if p.is_bid else seat.base_atoms
    need = (p.quote_atoms() if p.is_bid else p.base_atoms) - have
    if need > 0:
        ixs.append(deposit(owner, market, quote if p.is_bid else base, need))
    return [*ixs, batch(owner, market, [], [p]), expand(owner, market)]


def reprice(
    m: Market, owner: Pubkey, base: Token, quote: Token, is_bid: bool, price: Decimal
) -> tuple[list[int], Place]:
    """Our orders to cancel on one side, and one order holding everything that side had."""
    mine = m.mine(owner, is_bid)
    seat = m.seat(owner) or Seat(owner, 0, 0)
    unit = order(is_bid, 1, price, base, quote)
    if is_bid:
        quote_free = seat.quote_atoms + sum(o.locked_quote() for o in mine)
        size = math.floor(quote_free / (unit.mantissa * Decimal(10) ** unit.exponent))
    else:
        size = seat.base_atoms + sum(o.base_atoms for o in mine)
    if size <= 0:
        raise SystemExit("nothing to reprice on that side")
    return [o.seq for o in mine], Place(is_bid, size, unit.mantissa, unit.exponent)


def reprice_ixs(
    m: Market, market: Pubkey, owner: Pubkey, base: Token, quote: Token, is_bid: bool, price: Decimal
) -> list[Instruction]:
    cancels, p = reprice(m, owner, base, quote, is_bid, price)
    return [batch(owner, market, cancels, [p]), expand(owner, market)]


def amend_ixs(
    m: Market,
    market: Pubkey,
    owner: Pubkey,
    base: Token,
    quote: Token,
    seq: int,
    size: int | None,
    price: Decimal | None,
) -> list[Instruction]:
    """Cancel one of our orders and replace it, in one transaction; unset size or price keeps the old one."""
    old = next((o for o in m.mine(owner, True) + m.mine(owner, False) if o.seq == seq), None)
    if old is None:
        raise SystemExit(f"no open order of yours with id {seq} — see `mm orders`")
    new = order(
        old.is_bid, old.base_atoms if size is None else size, old.price if price is None else price, base, quote
    )
    seat = m.seat(owner) or Seat(owner, 0, 0)
    freed = old.locked_quote() if old.is_bid else old.base_atoms
    have = (seat.quote_atoms if old.is_bid else seat.base_atoms) + freed
    need = (new.quote_atoms() if new.is_bid else new.base_atoms) - have
    deposit_ix = [deposit(owner, market, quote if new.is_bid else base, need)] if need > 0 else []
    return [*deposit_ix, batch(owner, market, [seq], [new]), expand(owner, market)]


def cancel_ixs(m: Market, market: Pubkey, owner: Pubkey, seqs: list[int]) -> list[Instruction]:
    ours = {o.seq for o in m.mine(owner, True) + m.mine(owner, False)}
    missing = [s for s in seqs if s not in ours]
    if missing:
        raise SystemExit(f"no open order of yours with id {', '.join(map(str, missing))} — see `mm orders`")
    return [batch(owner, market, seqs, [])]


def cancel_all_ixs(m: Market, market: Pubkey, owner: Pubkey) -> list[Instruction]:
    seqs = [o.seq for o in m.mine(owner, True) + m.mine(owner, False)]
    return [batch(owner, market, seqs, [])] if seqs else []


def withdraw_all_ixs(m: Market, market: Pubkey, owner: Pubkey, base: Token, quote: Token) -> list[Instruction]:
    seat = m.seat(owner)
    if seat is None:
        return []
    return [
        ix
        for token, atoms in ((base, seat.base_atoms), (quote, seat.quote_atoms))
        if atoms
        for ix in (create_ata(owner, token), withdraw(owner, market, token, atoms))
    ]


def withdraw_free_ixs(
    m: Market, market: Pubkey, owner: Pubkey, token: Token, is_base: bool, atoms: int | None
) -> list[Instruction]:
    """Withdraw funds that are free in the seat — never what rests in orders. atoms None means all free."""
    seat = m.seat(owner)
    free = (seat.base_atoms if is_base else seat.quote_atoms) if seat else 0
    if not free:
        raise SystemExit(
            f"nothing free to withdraw — {token.symbol} resting in orders comes back with `mm cancel` or `mm exit`"
        )
    atoms = free if atoms is None else atoms
    if atoms > free:
        raise SystemExit(
            f"only {format(token.ui(free).normalize(), 'f')} {token.symbol} is free — the rest is in orders"
        )
    return [create_ata(owner, token), withdraw(owner, market, token, atoms)]
