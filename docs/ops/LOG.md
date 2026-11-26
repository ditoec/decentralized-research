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
- 08:02 UTC · runpod · RTX 4090 `sd06bsvyyfmec5` staged (14 tars verified in about 5 min at about 75 MB/s), released 08:02:14, self-delete received 08:02:35, gone by 08:02:40. Pod lifetime 17:55:13–08:02:36 ≈ 14.1 h × US$0.89 ≈ US$12.60, of which about 7 h was generation and the rest waiting on the Spark link · runbook §4
- 08:03 UTC · pull · Spark-5 switched the RTX 4090 pull and release to the staging copy (old processes stopped; 12/26 runs already home; the partial tar resumes from staging)
- 08:13 UTC · runpod · RTX 5090 L3 `ovdiegthi61b8w` staged (7 tars, about 38 GB, in about 13 min), released 08:12:56 and deleted itself; lifetime 01:41:19–about 08:13 ≈ 6.5 h × US$1.39 ≈ US$9.10. Spark-5 switched its pull and release to staging at 08:13:57 · runbook §4
- 08:21 UTC · measure · Pods left: RTX 3090 (run 13 of 14 at 539/600, then one 150-job run; DONE expected about 09:00) and the staging pod (US$0.12/h). On Spark-5: RTX 4090 13/26 runs, RTX 5090 L3 8/14, RTX 3090 2/14; pulls at 0.5–0.9 MB/s each, about 2.2 MB/s in total; balance US$14.45
- 08:22 UTC · spark · Grid: no failed jobs; Spark-4 72 runs, Spark-5 32, Spark-6 26; free memory 29–37 GB, free disk 361–457 GB
- 08:48 UTC · measure · RTX 3090 on its last run (14/14, 130/150); staging holds the RTX 4090 and 5090 copies (12.2 and 45.7 GB). Spark-5: RTX 4090 13/26, RTX 5090 L3 8/14, RTX 3090 2/14 runs; pulls 0.4–0.9 MB/s each, no checksum errors; balance US$14.18; grid no failed jobs, free memory 35–37 GB, free disk 358–455 GB
- 08:55 UTC · repo · Pushed the branch (staging tools, pull retry fix, L2/4090/5090 ends, ops log through 08:48 UTC); estimate: pulls to Spark-5 finish about 18:00–01:00 UTC, RTX 3090 ends about 09:15 UTC
- 08:52 UTC · runpod · RTX 3090 finished generating (14/14 runs) and received its draw seed (revealed by the threaded `pull_run.py` on Spark-5)
- 09:25 UTC · runpod · RTX 3090 still extracting retention bundles (precision runs class I 2.59 GB → 40 MB each; SD1.5 test runs class O 2.69 GB → 1.08–1.31 GB; SDXL test runs in progress), so not yet DONE or staged; later than the 09:15 estimate. Balance US$13.79. Spark-5: RTX 4090 13/26, RTX 5090 L3 8/14, RTX 3090 2/14 runs, no checksum errors
- 09:25 UTC · spark · Grid: no failed jobs; Spark-4 72 runs, Spark-5 33, Spark-6 27; free memory 26–36 GB (Spark-4 lowest), free disk 353–455 GB
- 09:56 UTC · decision · Operator: put the L2 subset on Sparks 1–3 and P3 "to go with the plan in the next"
- 09:56 UTC · spark · Sparks 1–3 checked read-only: no research setup; free memory 51 / 25 / 42 GB, free disk 608 / 716 / 444 GB, GPU idle
- 10:00 UTC · spark · Setup copy to Sparks 1–3 started from Spark-4 over the LAN at low priority (image 4.2 GB, code at `58f57c6`, configs, SDXL 6.5 GB), via ssh agent forwarding, so no keys are added to production nodes · runbook §4 item 1
- 10:04 UTC · spark · Setup on Sparks 1–3 done (about 140 s each) and verified against Spark-4: same image ID, same code and configs checksum, SDXL sha256 matches `models.json`
- 10:05 UTC · spark · L2 timers started on Sparks 1–3: at 18:00 UTC (01:00 local) each runs `ITEMS=l2` (150 SDXL jobs, class F) with `TRAJVER_GIT_COMMIT=58f57c6`; `spark_run.py` holds a run until 35 GB is free (Spark-2 had 25 GB at 17:00 local) · `~/esj/logs/wp2-l2-spark{1,2,3}.log`
- 10:05 UTC · decision-needed · P3 scheduled on Spark-1 after its L2 run, at a busy hour and in a quiet window; the quiet window (chat model stopped) and the platform's off-peak hours must come from the admin
- 10:12 UTC · decision · Operator: run L2 now rather than at 01:00 local; for P3, approved stopping the production chat model `vllm-chat` on Spark-3 for about 15–20 min and starting it again ("Yes, Spark-3 vllm-chat"), busy-hour P3 first
- 10:12 UTC · spark · L2 timers cancelled and L2 started now: Spark-1 started (54.5 GB free), Spark-3 started (44.3 GB free), Spark-2 waiting for memory (26.6 GB free, needs 35 GB)
- 10:14 UTC · spark · Spark-1 checked read-only: no chat model there; its GPU is shared by production ComfyUI (21 GB), `vllm-embed`, `vllm-rerank` and `agp-kyc`, so P3 moved to Spark-3, whose GPU is used only by `vllm-chat` (64 GB)
- 10:18 UTC · code · `tools/workloads/p3_spark.sh`: P3 on a Spark as the pilot ran it (pilot20, seed 0, 21 jobs, first excluded; SD1.5 512, SDXL 1024; no trajectories), labelled busy or quiet; SD1.5 copied to Spark-3 (sha256 checked)
- 10:15 UTC · runpod · RTX 3090 `r55nf5uam01yew` staged (12 tars, about 46 GB) and released 10:15:25; gone. Lifetime 22:34:21–about 10:16 ≈ 11.7 h × US$0.50 ≈ US$5.85; retention extraction after generation took about 80 min. Spark-5 switched to staging 10:16:55. No GPU pod left · runbook §4
- 10:25 UTC · measure · Balance US$13.17; only the staging pod and volume bill (about US$0.13/h). Spark-5: RTX 4090 15/26, RTX 5090 L3 8/14, RTX 3090 7/14 runs, no checksum errors. Grid: no failed jobs, free memory 26–37 GB, free disk 345–454 GB
- 10:50 UTC · spark · L2: Spark-1 done (150/150 jobs); Spark-3 at 101/150 (slower beside `vllm-chat`), P3 follows it; Spark-2 still waiting for memory (25 GB free, needs 35 GB). No failed jobs on any Spark
- 10:50 UTC · pull · Spark-5 from staging: RTX 4090 22/26, RTX 5090 L3 8/14, RTX 3090 9/14 runs, no checksum errors; balance US$13.12. Grid: Spark-4 72 runs, Spark-5 34, Spark-6 28; free memory 33–37 GB, free disk 341–454 GB
- 10:57 UTC · spark · L2 on Spark-3 done (150/150 jobs)
- 11:05 UTC · measure · P3 busy on Spark-3 (`vllm-chat` serving): SD1.5 median 1.84 s/image (p95 1.86), SDXL 12.32 (p95 15.15), n = 19 each · runs `20261126-wp0b-p3-*-busy-spark3-01`
- 11:07 UTC · spark · Production `vllm-chat` on Spark-3 stopped 11:07:16 for the P3 quiet window (operator's approval), with a trap to restart it on any exit
- 11:12 UTC · measure · P3 quiet on Spark-3: SD1.5 median 1.84 (p95 1.88), SDXL 12.04 (p95 12.32), n = 19 each. Co-tenancy moves the SDXL tail, not the median · runs `20261126-wp0b-p3-*-quiet-spark3-01`, runbook §3 finding 17
- 11:16 UTC · spark · `vllm-chat` started 11:12:36, healthy 11:16:26 (about 9 min out of service), serving again (64 GB on the GPU); no research container left on Spark-3
- 11:12 UTC · pull · RTX 4090 fully home on Spark-5: 26/26 runs pulled and checksum-verified, `trajver.retention check` passed, its staging copy released by Spark-5
- 11:25 UTC · repo · Catalog: 26 RTX 4090 runs added (`runs.csv` rows; their contact sheets stay on Spark-5 until the link is free). Spark-5 from staging: RTX 5090 L3 8/14, RTX 3090 9/14 runs, no checksum errors; balance US$13.04; Spark-2 L2 still waiting for memory (25 GB free); grid no failed jobs, free memory 33–37 GB, free disk 337–453 GB · `docs/ops/catalog/wp2/runs.csv`
- 12:49 UTC · pull · From staging: RTX 5090 L3 8/14, RTX 3090 9/14 runs (large SDXL tars in progress), now about 1.6 MB/s each (3.2 MB/s total, up from 2); no checksum errors; balance US$12.86. Spark-2 L2 still waiting for memory (25 GB free). Grid: no failed jobs; Spark-4 72 runs, Spark-5 37, Spark-6 30; free memory 35–37 GB, free disk 324–451 GB
- 12:53 UTC · repo · PR #11 merged into main as `343ba86` (staging pod, pull retry, L2 on Sparks 1–3, P3 busy vs quiet, ops log through 12:49 UTC)
- 12:53 UTC · decision · Operator: on Spark-2, and on other Sparks when necessary, pause production processes to free memory and resume them afterwards. Done as `docker stop` / `docker start` (`docker pause` keeps memory) · runbook §1 rule 1 exception
- 12:54 UTC · spark · Spark-2: production `vllm-asr` (about 14 GB) stopped 12:54:14 (free memory 25 → 43 GB); the waiting L2 run started 12:54:22. A node-side script restarts `vllm-asr` when L2 finishes and checks it is healthy (trap on any exit) · `~/esj/logs/free-mem-spark2.log`
- 12:57 UTC · repo · `docs/12-progress-for-paper.md`: progress summary for the paper (settled results by placeholder, protocol requirements, WP2 data status, infrastructure material, figures, open items, caveats)
- 13:28 UTC · run · Spark-2 L2 run `20261126-wp2-l2-sdxl-fp16-sdpa-euler-nd-spark2-01` done (150 jobs); production `vllm-asr` start issued 13:28:25, healthy 13:29:15 (node-side script, log on the node). L2 subset now complete on Sparks 1–3
- 14:39 UTC · pull · From staging: RTX 4090 26/26 home; RTX 5090 and RTX 3090 23 runs home in total, 2 in progress (one curl HTTP/2 reset, resumed by the retry loop); pulls and releases still running on Spark-5
- 14:55 UTC · repo · Metadata (no raw/, no images) of 147 newly completed runs fetched from the six Sparks into `experiments/runs/` and pseudonymised with `sanitize_runs.py`. A shell word-splitting slip first re-copied already committed runs over their sanitized versions; reverted with `git checkout` before anything was committed
- 14:58 UTC · fix · `sanitize_runs.py --check` compared JSON text, so old files with compact JSON failed without any leak (9 files, no host or address present). The check now compares parsed content (deep copy, since `scrub_obj` mutates) and still catches a co-tenant name and a host name in a synthetic test; whole tree exits 0
