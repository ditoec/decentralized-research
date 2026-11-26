# WP5 item 3 on Devnet (2026-11-26)

Runbook §7 item 3 asks for at least 100 Devnet jobs per lifecycle path. **Done:** 100 successful jobs per
path, 2,500 counted transactions, in `experiments/runs/20261126-wp5-devnet-replay-03/` plus its top-up `-04`.
The result is `combined_summary.json` there. Nothing was paid and no SOL was bought; the operator funded
the payer from the Devnet web faucet (5 + 4 SOL). The operator also decided "Stay on Devnet" (no Mainnet;
the Mainnet fee stays calculated).

## Result (combined, successful jobs)

| Path | Jobs | OK | Failed (client-side / other) | Confirm median / p95 (ms) | No 429: median / p95 (ms) | Mean CU per tx | CU per job (median) | Signatures per job | Fee per job (lamports) |
|---|---|---|---|---|---|---|---|---|---|
| unsampled | 104 | 100 | 2 / 2 | 1366 / 5627 | 1319 / 1908 | 15608.8 | 77831 | 5 | 25000 |
| pass | 104 | 100 | 0 / 4 | 1401 / 5746 | 1328 / 1899 | 14006.3 | 97695 | 7 | 35000 |
| dispute | 110 | 100 | 4 / 6 | 1399 / 5843 | 1325 / 1837 | 12543.8 | 125352 | 10 | 50000 |
| timeout | 103 | 100 | 1 / 2 | 1388 / 5777 | 1339 / 1820 | 21029.8 | 63343 | 3 | 15000 |

Copied from `SUMMARY.md` in the run folder; that file and `combined_summary.json` are the source.
The p95 of about 5.7 s is driven by the public RPC's rate limit on `getSignatureStatuses` (each 429 adds
backoff on the client); without the transactions that met a 429 the p95 is about 1.9 s. Read the run's
`README.md` for the caveats (failed jobs, latency method, the superseded `summary.json`).

## The way there (all in `docs/ops/LOG.md`)

1. Funding: the Devnet RPC faucet is closed (below). The operator funded the payer from the web faucet.
2. Deploy at 15:06 UTC, the local run's binary at its declared id (`solana program dump` sha256 matches).
3. Attempt 1 crashed in setup on a 429; attempt 2 crashed after 12 jobs on an unhandled 429 from the
   websocket confirmation (`-01`, kept, `CRASHED.md`); attempt 3 hit Job PDAs left by attempt 2 (removed,
   no records); attempt 4 had latencies inflated by silent 429 backoff (`-02`, kept, `STOPPED.md`).
   Fixes: confirmation by polling, a client-side throttle, 429s counted per transaction, unique job ids
   per run, failures kept and counted.
4. Attempt 5 (`-03`): 400 jobs, 21 failed with `fetch failed`, 7 of them during the operator's network
   change; the top-up `-04` (21 jobs, all OK) brought each path to 100.

## Funding: the original stop (kept for the record)

The first funding attempt stopped before the deploy, because no Devnet SOL could be obtained without a person.

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

## What was ready at the stop

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

## State after the run

The payer holds 5.83808576 SOL (Devnet) and stays the upgrade authority of the Devnet program. The actors'
leftover SOL was swept back after each attempt. The real time for 400 jobs was 2 h 17 min.
