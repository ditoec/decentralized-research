# WP5 item 3 on Devnet: stopped at funding (2026-11-26)

Runbook §7 item 3 asks for at least 100 Devnet jobs per lifecycle path. This attempt stopped before the
deploy because no Devnet SOL could be obtained without a person. Nothing was deployed, no transaction was
sent, and no run folder was written. Nothing was paid, and no SOL was bought.

## What happened

- 14:40 UTC: a fresh payer keypair was generated into `code/program/.anchor/devnet/` (git-ignored, not
  committed). Its public key is `EfAXuBFm3758x5ure2d14Etq5CSWTdioEyRhhVX6wkzy`.
- 14:40–14:48 UTC: Devnet airdrops were requested with `solana airdrop` (2 SOL and 1 SOL) and with a
  direct `requestAirdrop` RPC call to `https://api.devnet.solana.com`, retried six times with backoff
  from 15 s to 240 s. Every attempt failed the same way:
  - CLI: `Error: airdrop request failed. This can happen when the rate limit is reached.`
  - RPC: `{"code": 410, "message": "The RPC faucet is closed on this cluster. Request test SOL at https://faucet.solana.com"}`
- The balance stayed at 0 SOL. The raw attempts are in [`data/airdrop-attempts.log`](data/airdrop-attempts.log).

The 410 is not a rate limit. The CLI message is misleading: the RPC faucet on the public Devnet endpoint is
closed. Devnet SOL now comes only from the web faucet, which needs a sign-in and a CAPTCHA. An agent may
not complete either, so a person has to request it.

## What is ready

- `code/program/scripts/replay.ts --cluster devnet` (see `code/program/README.md`, "Path replay on Devnet").
  It refuses mainnet URLs, and any RPC with Mainnet's genesis hash. It funds the actors from the payer by
  transfer, uses real slot deadlines for the timeout path (`exec_timeout` = 2 slots), and writes
  `experiments/runs/<date>-wp5-devnet-replay-NN/`. The program logic is unchanged.
- The binary to deploy is the one from the local run (`program_so_sha256` `d4837478…ea70`). It is deployed at
  its declared id `HmMX8b7GLwUeJv4dw42xHAryRVfQm319ArWNbfj9ePpf`, which is not on Devnet yet.
- The smoke test was one round per path on a local validator with the changed script: 8 of 8 jobs closed in
  the expected state. It was not kept as a run.

## Budget for a full run (Devnet rent, read with `solana rent` on 2026-11-26)

| Item | SOL |
|---|---|
| Program data account (353,816-byte binary) | 1.80 (locked) |
| Deploy buffer | 1.80 (refunded after the deploy) |
| Job accounts: 400 × 0.00323 (never closed) | 1.29 (locked) |
| Fees, mint, token and bond accounts, actor margin | about 0.4 |
| **Peak / kept** | **about 5.3 / about 3.5** |

## To resume

1. A person requests Devnet SOL for `EfAXuBFm3758x5ure2d14Etq5CSWTdioEyRhhVX6wkzy` at faucet.solana.com,
   about 6 SOL in all (it may take two requests).
2. Then run the deploy and replay commands in `code/program/README.md`, "Path replay on Devnet". The run
   takes about 1 to 1.5 hours, at roughly 1 s per confirmed transaction over about 3,300 transactions,
   including the uncounted config updates.
