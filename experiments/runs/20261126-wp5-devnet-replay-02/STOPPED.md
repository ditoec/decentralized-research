# Stopped attempt: not a result

Attempt 4 of the WP5 Devnet replay, 2026-11-26 15:15–15:38 UTC. It was stopped by hand after 42 jobs
(265 transactions in `txs.jsonl`, all jobs complete up to the stop). The time to confirmed was bimodal,
about 1 s or about 5 s (median 4.8 s), and the extra ~3.5 s matches the client's silent 429 backoff
(0.5 + 1 + 2 s). The latencies are therefore client artefacts. Signatures, compute units and fees are
real Devnet values, but there is no summary or manifest. Do not use it; the clean run is
`20261126-wp5-devnet-replay-03`.
