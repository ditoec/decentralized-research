# Operations log

One line per action, newest day last; format and rules in [`README.md`](README.md). Times are UTC;
`~` marks a time reconstructed afterwards from commits or tool output. Entries before 2026-11-25 are in
`docs/07-runbook.md` §3–§4 and `docs/pilot-findings/`.

## 2026-11-25

- ~17:00 UTC · decision · Grid and precision factor cut to 50 prompts (`prompts_grid50.txt`, a subset of `prompts_prec100.txt`), same set on every non-reference config; grid on Sparks 4–6; never change DGX clocks or override `DATE` · docs 05 §4, 10 §2.3, runbook §4
- ~17:30 UTC · spark · WP2 grid launched on Spark-5 and Spark-6 (`ref grid l2`, 50 prompts × 3 seeds); Spark-4's first launch appended to the dry-run folder of the same UTC date, was stopped, and a waiter now starts it at the next UTC date · runbook §4
- 17:55 UTC · runpod · RTX 4090 pod `sd06bsvyyfmec5` created: Secure, EU-RO-1, US$0.89/h, 200 GB, items `ref prec slice`, `REP=02` (dry-run IDs on the same date); RTX 5090 and RTX 3090 had no stock in either cloud; balance US$24.49 · runbook §4
- 17:55 UTC · pull · `pull_run.py --wait --reveal-seed` started on Spark-5 for the 4090 · `~/esj/logs/pull-wp2-rtx4090.log`
- ~18:00 UTC · repo · PR #9 merged (grid50 and launch record) as `70b6308`
- 19:34 UTC · runpod · Hourly check: Community RTX 3090 listed at US$0.22/h but sold out between stock read and create (400, nothing billed); RTX 5090 only on Secure at US$1.39/h, held for budget (balance US$22.99) · runbook §4
- 22:34 UTC · runpod · RTX 3090 pod `r55nf5uam01yew` created: Secure, EU-CZ-1, US$0.50/h, items `ref prec`, own draw seed; pull started on Spark-5; balance US$20.24 · runbook §4
- 23:34 UTC · incident · First RTX 5090 pod `o6vqa6r4x5pds1` (Community, US$0.69/h, Threadripper 3960X, driver 580.178): `nvidia-smi` showed the card, PyTorch "CUDA unknown error"; terminated after about 2 min, before any job · runbook §4

## 2026-11-26

- 00:00 UTC · spark · Spark-4 waiter saw the new UTC date and started `ref l0 grid l2` with the grid seed · `~/esj/logs/wp2-grid50-spark4b.log`
- ~00:40 UTC · decision · Operator: RTX 5090 to "wait for Community"; a 5-minute stock check replaced the hourly one for the 5090 · memory, cron
- ~01:00 UTC · runpod · Community RTX 5090 (CUDA 12.9 host) listed; two creates refused for capacity, nothing billed
- 01:05 UTC · runpod · RTX 4090 finished generating (26 runs) and waited for its draw seed
- 01:19 UTC · incident · `pull_run.py` was inside a 17 GB class-F download (0.4–2 MB/s) and would reveal the seed only afterwards; seed revealed by hand through `pull_run.reveal()` (hash-checked) · runbook §4
- ~01:35 UTC · code · `pull_run.py` reveals the seed from its own thread; tested on a fake pod (seed at 0.2 s during a slowed download; wrong seed refused with exit 4); 3090 pull restarted on it · commit `45944c1`
- ~01:38 UTC · decision · Operator: "just look for rtx 5090 in both way, no need to stick just on community"
- 01:41 UTC · runpod · RTX 5090 (L3) pod `ovdiegthi61b8w` created: Secure, EUR-IS-2, US$1.39/h, EPYC 9554, driver 595.112, items `ref prec`, own draw seed; pull started; balance US$15.68 · runbook §4
- 03:45 UTC · measure · Balance US$9.97 with three pods at US$2.78/h; RTX 4090 pull 11/26 runs
- 03:55 UTC · measure · Spark site link is the bottleneck: pulls 0.35 / 0.86 / 0.60 MB/s; single tests from Sparks 0.4–0.5 MB/s; Spark-5 to a public speed test 0.6 MB/s; same pod to a laptop elsewhere 5.9 MB/s · ops report `2026-11-26-wp2-rentals/data/pull_throughput.csv`
- 03:55 UTC · runpod · Operator top-up of US$20; balance US$29.49
- ~03:57 UTC · decision · Operator kept pulling the 4090's last 14 GB to the Spark (about 11 h, about US$10 of idle pod) rather than via a laptop
- 04:02 UTC · code · Pods end themselves: `release_pod.py` on Spark-5 (pulled + checksum-verified + `trajver.retention check` → PUT `secret/release`) and `pod_selfstop.sh` on each pod (deletes itself with the pod-scoped key); tested on a fake pod and API; installed on the 4090, 3090 and 5090 · commit `678db23`, runbook §4
- ~04:05 UTC · runpod · Second RTX 5090 (L2) create on Secure refused for capacity, nothing billed
- 04:11 UTC · measure · Sparks 4–6: GPU 90–96%, unified memory 67–71% used, 406–476 GB disk free, no failed jobs · ops report `2026-11-26-wp2-rentals/data/spark_status_2026-11-26T0411Z.csv`
- 04:12 UTC · repo · Ops report `docs/ops/2026-11-26-wp2-rentals/` (screenshot, data, four charts) committed and pushed · commit `bd57e8f`
- 04:14 UTC · runpod · Second RTX 5090 (L2) pod `0u5abh48txmasr` created: Secure, EU-RO-1, US$1.39/h, Ryzen 9 7950X (different host from L3), item `l2` (class F, no seed); self-stop, pull and release started; 5-minute check deleted · commit `384ee1d`
- ~04:20 UTC · repo · PR #10 opened (self-stop tools, threaded reveal, runbook, ops report)
- ~04:25 UTC · decision · Operator: "keep logging on every processes that we do, document it somewhere in this project, we will use it for future writings"; this log and `docs/ops/README.md` created
- ~04:30 UTC · decision · Operator: the log "includes documenting the results of image generated, and everything that became input and output"
- ~04:35 UTC · code · `code/tools/run_catalog.py`: per-run inputs (code, ComfyUI, image digest, models and sha256, prompt set, seeds, sampler, precision, flags, retention, hardware, place, rate) and outputs (jobs, image hashes, images on disk, sizes, mean s/job, cost), contact sheets, and same-job comparisons across hardware
- ~04:40 UTC · spark · Catalog built on Sparks 4–6 (59, 73 and 25 runs, including Spark-4's dry run of 2026-11-25) and same-job sheets for `p00006_s0`/`_s1` (SD1.5 on Spark-5, RTX 4090, 3090, 5090; SDXL on Spark-5 and RTX 4090, the others not pulled yet) · `docs/ops/catalog/wp2/`
- ~04:45 UTC · repo · Logging convention in `docs/ops/README.md`, rule in `CLAUDE.md`; the hourly watch now appends here and refreshes the catalog when a pod ends
- ~05:30 UTC · incident · Copying contact sheets from Spark-5 to the repo ran at about 1 KB/s (the site link is saturated by four pulls) and one SSH connection timed out; stopped after 34 of Spark-5's 73 sheets. In the repo: all of Spark-4's sheets, 34 of Spark-5's, none of Spark-6's yet; `runs.csv` covers all 155 runs. The rest is fetched when the pulls finish · `docs/ops/catalog/wp2/`
- ~05:35 UTC · measure · Same prompt and seed (`p00006_s0`, `p00006_s1`) look identical by eye across Spark-5, RTX 4090, RTX 3090 and RTX 5090 (SD1.5) and across Spark-5 and RTX 4090 (SDXL); the numeric comparison is WP2's analysis, not this sheet · `docs/ops/catalog/wp2/compare/`
- 05:26 UTC · repo · PR #10 merged into main as `24ab33d` (self-stop tools, threaded reveal, ops report, logging convention, run catalog)
- 05:36 UTC · runpod · Second RTX 5090 (L2) `0u5abh48txmasr` finished generating (1 run, 2.7 GB) and waits on its pull; RTX 4090 pull 12/26 runs (about 12 GB left); RTX 3090 on run 12 (SDXL dpmpp_2m reference, 287/900, 8.4 s/job); RTX 5090 L3 on run 12 (682/900, 2.9 s/job); all four pull and four release processes alive on Spark-5
- 05:40 UTC · measure · About 100 GB still to pull (4090 ≈12 GB, L2 ≈2.7 GB, 3090 and 5090 ≈45 GB each including runs not yet generated) at about 2 MB/s ≈ 14 h; four pods bill US$4.17/h; balance US$22.56 would run out in about 6–8 h, and RunPod stops every pod at zero
- 05:42 UTC · decision-needed · Options put to the operator: top up about US$30 more, or a CPU staging pod (2 vCPU US$0.06/h) that takes each finished pod's tars at in-cloud speed so the GPU pod can be deleted, with Spark-5 pulling from the staging pod
- 05:42 UTC · spark · Grid: no failed jobs; Spark-4 64 runs, Spark-5 31, Spark-6 25; free memory 35–39 GB, free disk 390–469 GB
- 06:02 UTC · runpod · Second RTX 5090 (L2) `0u5abh48txmasr` ended by itself: pull verified 06:02:05, retention check 150/150, released 06:02:07, gone 06:02:38. First real use of the self-stop, with the operator's laptop not involved. About 1.8 h × US$1.39 ≈ US$2.50, of which 7 min was generation · runbook §4
- 06:36 UTC · runpod · Balance US$19.06; RTX 4090 pull still 12/26 (a 1.3 GB class-O tar at about 0.35 MB/s); RTX 3090 2 runs pulled, RTX 5090 L3 2; six pull and release processes alive
- 06:36 UTC · spark · Grid: no failed jobs; free memory 35–37 GB, free disk 379–464 GB
- 06:40 UTC · repo · Catalog row and contact sheet for `20261126-wp2-l2-sdxl-fp16-sdpa-euler-nd-rtx5090b-01` added · `docs/ops/catalog/wp2/`
- ~07:00 UTC · incident · All three pull processes (RTX 4090, 3090, 5090) died with curl errors after curl's own 8 retries, most likely a link outage on the Spark side (an SSH connection to Spark-5 had timed out earlier). Partial tars kept; release processes unaffected · `~/esj/logs/pull-wp2-*.log`
- 07:36 UTC · runpod · RTX 5090 L3 finished generating (14 runs, DONE); RTX 3090 on run 13 (SDXL dpmpp_2m test, 227/600); balance US$16.20 at US$2.78/h
- 07:45 UTC · code · `pull_run.py` now keeps resuming a download after curl gives up (every 60 s) and retries reading READY, INDEX and checksums instead of crashing; tested on a fake pod whose first tar request fails (resumed and verified), reveal test still passes; installed on Spark-5 and the three pulls restarted (downloads resumed from the partial tars)
- 07:47 UTC · spark · Grid: no failed jobs; free memory 35–38 GB, free disk 369–461 GB
- 07:51 UTC · measure · Left to pull: RTX 4090 ≈7.5 GB (12/26 runs home), RTX 5090 L3 ≈44.7 GB (7/14), RTX 3090 ≈36 GB (2/14; still generating run 13 of 14, about 1 h left). About 88 GB at the measured 1.2–2 MB/s ≈ 12–14 h. Estimated pod cost to finish: 4090 ≈US$3, 3090 ≈US$6, 5090 ≈US$19, ≈US$28 in all against a balance of US$15.49; runs out around 14:30 UTC without a top-up of about US$25–30
- 07:55 UTC · decision · Operator chose the staging pod over a top-up ("use staging pods")
- 07:56 UTC · code · `tools/stage_copy.py`, `tools/stage_selfstop.sh`, `tools/stage_switch.sh` written; `release_pod.py` retention-check container named per process; full staged chain tested on fake pods and API (skip, late DONE, release, switch, both deletions) · runbook §4
- 07:57 UTC · runpod · Network volume `xgzm7eis58` (120 GB, EU-RO-1, about US$0.01/h) and staging CPU pod `twazk132j21s05` (cpu3c 4 vCPU, Secure, EU-RO-1, US$0.12/h) created; a 150 GB container disk was refused (CPU pods allow 40 GB)
- 08:02 UTC · pull · Staging copy started for the RTX 4090 (14 tars to copy, 12 already on Spark-5), RTX 5090 L3 (7 to copy, 7 on Spark-5) and RTX 3090 (waits for DONE; 2 on Spark-5); about 75 MB/s in-cloud. Stage switches started on Spark-5 for all three
