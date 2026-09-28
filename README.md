<img width="1200" alt="Labs" src="https://user-images.githubusercontent.com/99700157/213291931-5a822628-5b8a-4768-980d-65f324985d32.png">

<p>
 <h3 align="center">Chainstack is the leading suite of services connecting developers with Web3 infrastructure</h3>
</p>

<p align="center">
  • <a target="_blank" href="https://chainstack.com/">Homepage</a> •
  <a target="_blank" href="https://chainstack.com/protocols/">Supported protocols</a> •
  <a target="_blank" href="https://chainstack.com/blog/">Chainstack blog</a> •
  <a target="_blank" href="https://docs.chainstack.com/quickstart/">Blockchain API reference</a> • <br> 
  • <a target="_blank" href="https://console.chainstack.com/user/account/create">Start for free</a> •
</p>

# Limit orders on World prediction markets

> [!NOTE]
> Experimental. A reference implementation, not for production use. It places real orders with
> real money; every command that sends only simulates until you pass `--send`.

Place your own limit orders on [World](https://world.xyz) outcome tokens. Your order rests on a
public Solana order book ([Manifest](https://github.com/CKS-Systems/manifest)), and World's router
fills it whenever your price is the best on offer.

How World works on chain: [world-xyz-research](https://github.com/chainstacklabs/world-xyz-research).

## How it fits

Most trades on Solana go through a **router** (or aggregator), which checks every **venue** for the
token pair and sends the whole trade to the best price for its size. For World's markets the
venues are World's own market maker and public order books, where anyone can rest a limit order.
World's app routes through DFlow's prediction-market router; Jupiter and other aggregators do the
same for their users.

```
World app ──► World's router (DFlow) ──┬──► World's market maker
                                       └──► public order book, e.g. Manifest ◄── your limit orders
Jupiter, other aggregators ────────────────┘
```

This repo implements the order-book side on Manifest: find World markets, get YES and NO tokens,
rest and manage your orders, and check that the routers pick your book (`mm probe`). Other
venues are in [TODO.md](TODO.md).

## What you need

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- A Solana mainnet RPC endpoint
- A new wallet with a little SOL, not your main one

Create the wallet with the [Solana CLI](https://solana.com/docs/intro/installation):

```bash
solana-keygen new --outfile ~/mm-wallet.json
solana-keygen pubkey ~/mm-wallet.json        # the address to fund
```

The file is the private key: keep it, and `.env`, out of git, and back it up.

## From SOL to a resting order

```bash
cp .env.example .env                        # set RPC_URL and WALLET_KEY
alias mm='uv run --env-file .env mm'

mm markets --search inflation --prices      # find a market
mm market <address>                         # its question, status and World's prices
mm use <address>                            # select it; every command below works on it
mm verify                                   # check its addresses on chain
mm swap sol cash 0.5                        # SOL -> CASH
mm split 10                                 # 10 CASH -> 10 YES + 10 NO
mm create                                   # only if `mm use` found no Manifest book
mm place ask 10 0.15                        # GTC limit order*: sell 10 YES at 0.15 CASH each
mm orders
```

\* A GTC (good-till-cancelled) limit order waits on the book at your price until someone takes it
or you cancel it, and never fills at a worse price than yours. If your price already beats the
other side, such as an ask below the best bid, it fills at once.

`mm use` writes the market to `market.json`: its tokens, World's accounts, and its Manifest book
if one exists. Switch markets with `mm use <address> --force`; trade NO with `--side no`, or both
sides at once with one file each (`MARKET_FILE=no.json`).

Every write simulates first. Add `--send` to execute: `mm` shows the simulation and asks before
sending; scripts and agents add `--yes` to skip the prompt.

```bash
mm place ask 10 0.15 --send                 # simulation, then: send on mainnet (real funds)? [y/N]
```

For the full list of commands, run `mm --help`; `mm <command> --help` shows its options. Read
commands take `--json` for scripts and agents.

## Practice on a fork

[surfpool](https://github.com/txtx/surfpool) runs a local copy of mainnet: real transactions
against real market state, and nothing reaches mainnet. Use a throwaway wallet.

```bash
mm fork start                                                     # terminal 1, forks from your RPC_URL
RPC_URL=http://127.0.0.1:8999 mm fork fund --sol 2 --cash 100     # terminal 2
RPC_URL=http://127.0.0.1:8999 mm place ask 10 0.15 --send --yes
```

surfpool charges more rent than mainnet, so on a fork `mm` tops up accounts copied from mainnet
before each transaction.

## Good to know

- **Complete sets.** 1 CASH mints 1 YES + 1 NO, and the pair redeems 1 CASH until the market
  resolves. YES pays 1 CASH if the event happens, NO if it doesn't.
- **Order types.** `mm` places Manifest limit orders. One whose price crosses the book fills at
  once, and `mm` warns you first. Other types are in [TODO.md](TODO.md).
- **Rent.** Creating a market locks its rent for good; `mm create` prints how much.
- **Settlement.** The issuer can burn outcome tokens anywhere at settlement, including in the
  market's vaults. Exit before a market resolves.
- **Data.** Markets, balances, books, and fills come from Solana; World's prices from its router;
  questions from `m.world.xyz`, cached in `~/.cache/mm/`; swaps from Jupiter.

## For agents

If you are an AI agent asked to extend this repo, take the next item from [TODO.md](TODO.md):

1. Read [AGENTS.md](AGENTS.md) first; its rules apply to every change.
2. Pick one item and tell the person which before you start.
3. Check how it works against the program's source. Experiment on a fork first
   ([Practice on a fork](#practice-on-a-fork)), where `--send --yes` is fine. On mainnet, only
   simulate. Note every fact you verify, with the date.
4. Tests first, then code. `uvx ruff format .`, `uvx ruff check .` and `uv run pytest` must be
   clean, and the new path must work on the fork and simulate cleanly on mainnet.
5. Update README.md and TODO.md, then show the diff and a commit message. Don't commit or send
   without the person's go-ahead.
