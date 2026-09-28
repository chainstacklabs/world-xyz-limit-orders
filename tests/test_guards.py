import pytest

from mmkit import guards
from mmkit.guards import confirm, fork_only, is_local

MAINNET = "https://solana-mainnet.example.com/abc"


def test_is_local():
    assert is_local("http://127.0.0.1:8999")
    assert not is_local(MAINNET)
    assert not is_local("https://evil.example.com/localhost")


def test_fork_only():
    fork_only("http://localhost:8999")
    with pytest.raises(SystemExit, match="fork only"):
        fork_only(MAINNET)


@pytest.fixture
def terminal(monkeypatch):
    monkeypatch.setenv("RPC_URL", MAINNET)
    monkeypatch.setattr(guards.sys.stdin, "isatty", lambda: True)
    asked = []

    def answer(reply):
        monkeypatch.setattr("builtins.input", lambda prompt: asked.append(prompt) or reply)
        return asked

    return answer


def test_yes_skips_the_prompt(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda p: pytest.fail("asked despite --yes"))
    confirm(yes=True)


def test_no_terminal_needs_yes(monkeypatch):
    monkeypatch.setenv("RPC_URL", MAINNET)
    monkeypatch.setattr(guards.sys.stdin, "isatty", lambda: False)
    with pytest.raises(SystemExit, match="add --yes"):
        confirm(yes=False)


@pytest.mark.parametrize("reply", ["y", "YES", " yes "])
def test_confirmed(terminal, reply):
    asked = terminal(reply)
    confirm(yes=False)
    assert asked == ["send on mainnet (real funds)? [y/N] "]


@pytest.mark.parametrize("reply", ["", "n", "sure"])
def test_anything_else_is_no(terminal, reply):
    terminal(reply)
    with pytest.raises(SystemExit, match="not sent"):
        confirm(yes=False)


def test_prompt_names_a_local_fork(terminal, monkeypatch):
    monkeypatch.setenv("RPC_URL", "http://127.0.0.1:8999")
    asked = terminal("y")
    confirm(yes=False)
    assert asked == ["send on the local RPC? [y/N] "]
