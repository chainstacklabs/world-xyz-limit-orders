import pytest
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction

from mmkit import guards, rpc, sim


@pytest.fixture
def fake_rpc(monkeypatch):
    calls = []
    result = {"err": None, "unitsConsumed": 1234, "logs": []}

    def call(method, params):
        calls.append(method)
        return {"simulateTransaction": {"value": result}, "sendTransaction": "SIG"}[method]

    monkeypatch.setenv("RPC_URL", "https://rpc.example.com")
    monkeypatch.setattr(rpc, "call", call)
    monkeypatch.setattr(rpc, "blockhash", Hash.default)
    monkeypatch.setattr(rpc, "confirm", lambda sig: None)
    return calls, result


def _ix():
    kp = Keypair()
    return kp, [Instruction(Pubkey.default(), b"", [AccountMeta(kp.pubkey(), True, True)])]


def test_dry_run_never_sends(fake_rpc, capsys):
    calls, _ = fake_rpc
    kp, ixs = _ix()
    assert sim.simulate_or_send(ixs, kp, send=False) is None
    assert calls == ["simulateTransaction"]
    assert "1234 CU" in capsys.readouterr().out


def test_send(fake_rpc):
    calls, _ = fake_rpc
    kp, ixs = _ix()
    assert sim.simulate_or_send(ixs, kp, send=True, yes=True) == "SIG"
    assert calls == ["simulateTransaction", "sendTransaction"]


def test_failed_simulation_prints_logs_and_stops(fake_rpc, capsys):
    calls, result = fake_rpc
    result.update(err={"InstructionError": [0, "Custom"]}, logs=["Program log: insufficient funds"])
    kp, ixs = _ix()
    with pytest.raises(SystemExit):
        sim.simulate_or_send(ixs, kp, send=True, yes=True)
    assert calls == ["simulateTransaction"]
    assert "insufficient funds" in capsys.readouterr().out


def test_sign_and_run_signs_an_external_transaction(fake_rpc):
    calls, _ = fake_rpc
    kp, ixs = _ix()
    unsigned = VersionedTransaction.populate(Message.new_with_blockhash(ixs, kp.pubkey(), Hash.default()), [])
    assert sim.sign_and_run(unsigned, kp, send=True, yes=True) == "SIG"
    assert calls == ["simulateTransaction", "sendTransaction"]


def test_unconfirmed_send_warns_before_a_retry(fake_rpc, monkeypatch, capsys):
    def slow(sig):
        raise rpc.RpcError("not confirmed after 60s")

    monkeypatch.setattr(rpc, "confirm", slow)
    kp, ixs = _ix()
    with pytest.raises(SystemExit, match="may still land"):
        sim.simulate_or_send(ixs, kp, send=True, yes=True)
    assert "SIG" in capsys.readouterr().out


def test_send_preflights_at_the_blockhash_commitment(monkeypatch):
    sent = []

    def call(method, params):
        if method == "sendTransaction":
            sent.append(params[1])
            return "SIG"
        return {"value": {"err": None, "unitsConsumed": 1, "logs": []}}

    monkeypatch.setenv("RPC_URL", "https://rpc.example.com")
    monkeypatch.setattr(rpc, "call", call)
    monkeypatch.setattr(rpc, "blockhash", Hash.default)
    monkeypatch.setattr(rpc, "confirm", lambda sig: None)
    kp, ixs = _ix()
    sim.simulate_or_send(ixs, kp, send=True, yes=True)
    assert sent == [{"encoding": "base64", "preflightCommitment": "confirmed"}]  # blockhash is fetched at "confirmed"


def test_simulation_retries_a_blockhash_not_yet_seen(monkeypatch):
    results = [
        {"err": "BlockhashNotFound", "unitsConsumed": 0, "logs": []},
        {"err": None, "unitsConsumed": 7, "logs": []},
    ]
    calls = []

    def call(method, params):
        calls.append(method)
        return {"value": results.pop(0)}

    monkeypatch.setenv("RPC_URL", "https://rpc.example.com")
    monkeypatch.setattr(rpc, "call", call)
    monkeypatch.setattr(rpc, "blockhash", Hash.default)
    monkeypatch.setattr(sim.time, "sleep", lambda s: None)
    kp, ixs = _ix()
    assert sim.simulate_or_send(ixs, kp, send=False) is None
    assert calls == ["simulateTransaction", "simulateTransaction"]


def test_send_without_confirmation_never_sends(fake_rpc, monkeypatch):
    calls, _ = fake_rpc
    monkeypatch.setattr(guards.sys.stdin, "isatty", lambda: False)
    kp, ixs = _ix()
    with pytest.raises(SystemExit, match="add --yes"):
        sim.simulate_or_send(ixs, kp, send=True)
    assert calls == ["simulateTransaction"]
