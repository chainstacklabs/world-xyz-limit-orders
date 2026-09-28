# world-xyz-limit-orders

`mm` — a Typer CLI for resting limit orders on World outcome tokens via Manifest.

## Run and check

- CLI: `uv run --env-file .env mm <command>`; `mm --help` lists every command.
- Before every commit: `uvx ruff format .`, `uvx ruff check .` and `uv run pytest` (offline), all
  clean. Settings in `pyproject.toml` (120-char lines).

## Real money

- Every write simulates first. Sending needs `--send` plus `y` at the prompt, or `--yes` without a
  terminal.
- On mainnet, only simulate unless the person says to send.
- Never read, print, or commit `.env`, `market.json`, or keypair files.
- No data from our own trading in code, tests, or docs: no wallet, market, transaction, or amount
  of ours. Fixtures are public chain data or synthetic.

## Experiment on a fork first

A surfpool fork is a local copy of mainnet: real transactions against real state, nothing reaches
mainnet. `--send --yes` is fine there. Use a throwaway wallet (`WALLET_KEY`), never a real one.

```bash
mm fork start                                            # terminal 1: forks from your RPC_URL
export RPC_URL=http://127.0.0.1:8999                     # terminal 2: shell variables beat .env
export WALLET_KEY=~/fork-wallet.json                     # a throwaway keypair (solana-keygen new)
mm fork fund --sol 2 --cash 100
mm split 10 --send --yes && mm place ask 10 0.15 --send --yes
```

- `fork start` forks from the person's `RPC_URL`, never surfpool's public `--network` shortcut.
- surfpool charges more rent than mainnet, so on a local RPC `sim.py` tops up accounts copied from
  mainnet before each transaction. Without that, growing a copied account fails with
  `InsufficientFundsForRent` while every program log says success.

## Code

- Simple over clever: plain functions and dataclasses, no registries or base classes.
- One command = one file in `mmkit/commands/`, under 50 lines, registered in `mmkit/cli.py`.
  Logic lives in `mmkit/`, where tests can call it.
- Read commands take `--json` and print JSON only; errors are one line on stderr.
- Comments only where the code can't speak: a byte offset, a program quirk, a trap.
- Docs and help are written for the person using the tool: what to do and what happens.

## Tests

- A behaviour change comes with the test that pins it, in the same commit.
- Every safety rule and every on-chain layout fact has a test.
- Check a layout against, most trusted first: a simulation on the deployed program, then a real
  mainnet transaction, then the SDK. The SDK can be wrong: Manifest's core deposit builder writes a
  field twice, so encode from the program's structs.
- A fact read from chain or program source carries a date in the test or comment that pins it.
