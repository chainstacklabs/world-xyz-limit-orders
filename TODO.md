# Venues to test

A venue gets a module only if it passes all three, in order:

1. Anyone can create a market for a World outcome token (Token-2022, permanent delegate).
2. World's router routes to it — both directions — and from what bid depth.
3. A fill spends no taker SOL.

| Venue | 1 | 2 | 3 | Fees | Rent back? | Notes |
|---|---|---|---|---|---|---|
| Manifest | yes | yes | yes, with a spare block | 0 | no | shipped |
| Phoenix | | | | | | |
| OpenBook v2 | | | | | | |

# Order types to add

`mm` places Manifest `Limit` orders only. Manifest's program has more; each needs its semantics
checked against the program source and a simulation before it ships.

| Type | What it's for |
|---|---|
| `PostOnly` | Rest only — refuse an order that would fill at once, so you never take liquidity |
| `ImmediateOrCancel` | Take what's there now, rest nothing |
| Expiring (`last_valid_slot`) | An order that stops being valid after a slot |
| `Reverse`, `ReverseTight` | After a fill, re-post the other side at a set spread — two-sided quoting that maintains itself |
| `Global` | Funds shared across several markets from one global account, instead of a deposit per market |
