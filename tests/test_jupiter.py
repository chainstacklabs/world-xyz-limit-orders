import pytest
from solders.pubkey import Pubkey

from mmkit import jupiter


def test_no_route(monkeypatch):
    monkeypatch.setattr(jupiter, "get_json", lambda url: {"error": "Could not find any route"})
    with pytest.raises(SystemExit, match="Jupiter has no route"):
        jupiter.quote(jupiter.SOL, Pubkey.default(), 1)


def test_quote_passes_amount(monkeypatch):
    seen = []
    monkeypatch.setattr(jupiter, "get_json", lambda url: seen.append(url) or {"outAmount": "5"})
    assert jupiter.quote(jupiter.SOL, Pubkey.default(), 10_000_000)["outAmount"] == "5"
    assert "amount=10000000" in seen[0] and "slippageBps=50" in seen[0]
