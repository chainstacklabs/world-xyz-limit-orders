import base64
import json
from pathlib import Path

import pytest
from solders.pubkey import Pubkey

from mmkit.config import load

FIXTURES = Path(__file__).parent / "fixtures"
# public SOL/USDC Manifest market, captured at slot 451071501
PUBLIC_MARKET = Pubkey.from_string("6q5qNNuEm8dAnzW5H6z1TrbzhXEUcGosrCmJb7pVLUPm")
# World BTC-UP market with a July 2026 window; market.json is `mm use` output for it
WORLD_MARKET = Pubkey.from_string("638vJXume9w4RMhxMUJLPgkoj8K9UhMJr2jKM8j6KWs")
OWNER = Pubkey.from_string("11111111111111111111111111111112")
MARKET = Pubkey.from_string("11111111111111111111111111111113")


def b64(name: str) -> bytes:
    return base64.b64decode((FIXTURES / name).read_text())


@pytest.fixture
def cfg():
    return load(FIXTURES / "market.json")


@pytest.fixture
def market_bytes():
    return b64("manifest_market.b64")


@pytest.fixture
def world_bytes():
    return b64("world_market.b64")


@pytest.fixture
def fill_tx():
    return json.loads((FIXTURES / "fill_tx.json").read_text())
