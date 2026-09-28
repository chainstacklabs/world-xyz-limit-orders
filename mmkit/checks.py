"""Is every address in market.json what it claims to be, on chain?"""

from mmkit import rpc, world
from mmkit.config import Config, Token
from mmkit.venue import manifest


def _program(key) -> bool:
    return bool((a := rpc.account(key)) and a.executable)


def _mint(t: Token) -> bool:
    a = rpc.account(t.mint)
    return bool(a and a.owner == t.program and a.data[44] == t.decimals)  # decimals sit at byte 44 of a mint


def _vault(cfg: Config) -> bool:
    a = rpc.account(cfg.issuer.collateral_vault)
    return bool(a and a.data[:32] == bytes(cfg.collateral.mint) and a.data[32:64] == bytes(cfg.issuer.ledger))


def _world_market(cfg: Config) -> bool:
    a = rpc.account(cfg.issuer.ledger)
    if not (a and a.owner == cfg.issuer.program and a.data[:8] == world.MARKET_DISC):
        return False
    m = world.parse_market(cfg.issuer.ledger, a.data)
    ours = (cfg.yes.mint, cfg.no.mint, cfg.collateral.mint, cfg.issuer.collateral_vault)
    return (m.yes_mint, m.no_mint, m.cash_mint, m.vault) == ours


def _book(cfg: Config) -> bool:
    a = rpc.account(cfg.market)
    m = manifest.parse(a.data) if a and a.owner == manifest.PROGRAM else None
    return bool(m and (m.base_mint, m.quote_mint) == (cfg.base.mint, cfg.quote.mint))


def run(cfg: Config) -> dict[str, bool]:
    tokens = {t.mint: t for t in (cfg.base, cfg.quote, cfg.counterpart, cfg.collateral)}.values()
    out = {"issuer program": _program(cfg.issuer.program), "manifest program": _program(manifest.PROGRAM)}
    out |= {f"{t.symbol} mint": _mint(t) for t in tokens}
    out |= {"world market": _world_market(cfg), "collateral vault": _vault(cfg)}
    if cfg.market:
        out["manifest market"] = _book(cfg)
    return out
