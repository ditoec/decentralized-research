# WP5 item 3 on Devnet: 100 jobs per path

The result is `combined_summary.json` (table in `SUMMARY.md`). It combines this run, which has 400
interleaved jobs (2026-11-26 15:42–17:59 UTC), with its top-up run `20261126-wp5-devnet-replay-04`
(21 jobs, 17:59–18:10 UTC). Together they give at least 100 successful jobs per path: 400 jobs and
2,500 counted transactions. The combined numbers come from `code/program/scripts/combine_replay.py`:

    python3 code/program/scripts/combine_replay.py experiments/runs/20261126-wp5-devnet-replay-03 \
      experiments/runs/20261126-wp5-devnet-replay-04 \
      --client-outage 2026-11-26T17:21:00Z/2026-11-26T17:30:00Z "operator switched the laptop's network (reported by the coordinating session)"

Read this before using the files here:
- **`summary.json` in this folder is superseded.** It was written by the replay before failed jobs were
  separated: its per-job statistics count each failed job as a job with zero transactions. Use
  `combined_summary.json`.
- **Failed jobs:** 21 of 400 in this run, every one a `fetch failed` (a dropped HTTP connection between the laptop
  and the RPC); none is a transaction error returned by the cluster. 7 fall inside 17:21–17:30 UTC, when the
  operator switched the laptop's network; they are counted as client-side. The other 14 (17:33–17:59 UTC)
  have no confirmed cause; a probe at 17:36 UTC saw Devnet RPC health checks time out or take 6–7 s
  while other sites answered in 0.3 s. They are counted as "other", not attributed to the client.
  This run did not write a failed job's partial transactions (those it sent are on chain but not listed);
  the top-up run and later replays do.
- Four failures happened in the uncounted config update before `create_job`. The replay of this run logged
  them under the previous job's id; `combine_replay.py` marks them "before create_job".
- **Latency:** wall-clock from send to `confirmed` as seen by the client over the public RPC
  (`api.devnet.solana.com`, free, no key), polled about every 0.45 s, with client-side request spacing.
  2,134 `getSignatureStatuses` calls were answered 429 and retried (no other method). Transactions that met
  a 429 have `rpc_429 > 0` in `txs.jsonl`; `ms_to_confirmed_per_tx_no_429` leaves them out.
- Signature counts, compute units and fees do not depend on the latency issues. All 2,500 counted
  transactions have their CU and fee; every fee is 5,000 lamports per signature (no priority fee).
  20 random signatures were checked with `getSignatureStatuses` on 2026-11-26: all finalized without
  error, in the recorded slots.
- CU per job differs from the local run (e.g. unsampled 77,831 here vs 82,326 locally) because the
  PDA bump search depends on the job id, and Devnet job ids start at a time-based base.
- The program binary is the local run's (`program_so_sha256` `d4837478…ea70`, checked against
  `solana program dump`). `program_tree_dirty` is true because the replay script was being changed;
  the script used is in the commit that adds this folder (the top-up used the later version with
  `--only` and connection retries).
- Earlier attempts, not results: `-01` (crashed), `-02` (stopped). See `docs/ops/LOG.md`, 2026-11-26.
