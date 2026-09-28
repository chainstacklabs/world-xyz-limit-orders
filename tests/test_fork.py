import pytest
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from typer.testing import CliRunner

from mmkit import cli, fork, rpc, sim, world
from mmkit.commands import fork as fork_cmd

MAINNET = "https://solana-mainnet.example.com/abc"


def test_surfpool_forks_from_your_rpc_only():
    args = fork.surfpool_args(MAINNET)
    assert args[:4] == ["surfpool", "start", "--rpc-url", MAINNET]
    assert "--network" not in args and ["--port", "8999"] == args[args.index("--port") : args.index("--port") + 2]
    assert {"--no-tui", "--no-studio", "--no-deploy", "-y"} <= set(args)
    assert "--ci" not in args  # --ci also silences surfpool's logs, so the fork terminal would look hung


def test_start_refuses_a_local_or_missing_rpc(monkeypatch):
    monkeypatch.setattr(fork_cmd.shutil, "which", lambda name: "/bin/surfpool")
    r = CliRunner().invoke(cli.app, ["fork", "start"], env={"RPC_URL": "http://127.0.0.1:8999"})
    assert r.exit_code != 0 and "your mainnet RPC_URL" in r.output
    r = CliRunner().invoke(cli.app, ["fork", "start"], env={})
    assert r.exit_code != 0 and "RPC_URL is not set" in r.output


def test_start_needs_surfpool(monkeypatch):
    monkeypatch.setattr(fork_cmd.shutil, "which", lambda name: None)
    r = CliRunner().invoke(cli.app, ["fork", "start"], env={"RPC_URL": MAINNET})
    assert r.exit_code != 0 and "surfpool not found" in r.output


def test_start_hands_over_to_surfpool_without_printing_the_url(monkeypatch):
    seen = []
    monkeypatch.setattr(fork_cmd.shutil, "which", lambda name: "/bin/surfpool")
    monkeypatch.setattr(fork_cmd.os, "execvp", lambda f, args: seen.append(args))
    r = CliRunner().invoke(cli.app, ["fork", "start"], env={"RPC_URL": MAINNET})
    assert seen == [fork.surfpool_args(MAINNET)] and MAINNET not in r.output and fork.FORK_URL in r.output


def test_fund_is_fork_only(monkeypatch, tmp_path):
    key = tmp_path / "k.json"
    key.write_text(str(list(bytes(Keypair()))))
    r = CliRunner().invoke(cli.app, ["fork", "fund", "--sol", "1"], env={"RPC_URL": MAINNET, "WALLET_KEY": str(key)})
    assert r.exit_code != 0 and "fork only" in r.output


def test_fund_sets_sol_and_cash(monkeypatch):
    calls = []
    monkeypatch.setattr(rpc, "call", lambda m, p: calls.append((m, p)))
    owner = Pubkey.new_unique()
    fork.fund(owner, 2 * 10**9, 50_000_000)
    assert calls[0] == ("surfnet_setAccount", [str(owner), {"lamports": 2 * 10**9}])
    assert calls[1] == (
        "surfnet_setTokenAccount",
        [str(owner), str(world.CASH), {"amount": 50_000_000}, "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"],
    )


def test_top_up_only_under_funded_accounts(monkeypatch):
    short, fine, missing = Pubkey.new_unique(), Pubkey.new_unique(), Pubkey.new_unique()
    accounts = {
        short: rpc.Account(bytes(100), 10, Pubkey.default(), False),
        fine: rpc.Account(bytes(100), 10**9, Pubkey.default(), False),
    }
    calls = []
    monkeypatch.setattr(rpc, "account", lambda k: accounts.get(k))
    monkeypatch.setattr(rpc, "rent", lambda size: 1_586_880)
    monkeypatch.setattr(rpc, "call", lambda m, p: calls.append((m, p)))
    assert fork.top_up([short, fine, missing]) == 1
    assert calls == [("surfnet_setAccount", [str(short), {"lamports": 1_586_880}])]


def test_top_up_skips_a_local_rpc_without_cheatcodes(monkeypatch):
    def call(m, p):
        raise rpc.RpcError("surfnet_setAccount: Method not found")

    monkeypatch.setattr(rpc, "account", lambda k: rpc.Account(bytes(10), 1, Pubkey.default(), False))
    monkeypatch.setattr(rpc, "rent", lambda size: 999)
    monkeypatch.setattr(rpc, "call", call)
    assert fork.top_up([Pubkey.new_unique()]) == 0


def test_writable_keys_from_the_header():
    payer, w, r = Keypair(), Pubkey.new_unique(), Pubkey.new_unique()
    ix = Instruction(Pubkey.new_unique(), b"", [AccountMeta(w, False, True), AccountMeta(r, False, False)])
    keys = fork.writable(Message.new_with_blockhash([ix], payer.pubkey(), Hash.default()))
    assert set(keys) == {payer.pubkey(), w}


@pytest.mark.parametrize(("url", "topped"), [("http://127.0.0.1:8999", True), (MAINNET, False)])
def test_sends_top_up_only_on_a_local_rpc(monkeypatch, url, topped):
    seen = []
    monkeypatch.setenv("RPC_URL", url)
    monkeypatch.setattr(rpc, "blockhash", Hash.default)
    monkeypatch.setattr(rpc, "call", lambda m, p: {"value": {"err": None, "unitsConsumed": 1, "logs": []}})
    monkeypatch.setattr(sim.fork, "top_up", lambda keys: seen.append(keys) or 0)
    kp = Keypair()
    sim.simulate_or_send(
        [Instruction(Pubkey.new_unique(), b"", [AccountMeta(kp.pubkey(), True, True)])], kp, send=False
    )
    assert bool(seen) is topped
