# WP2 rentals and Spark grid, 2026-11-25/26: operations report

This report records the night the WP2 (RQ1) runs were started on rented GPUs and on Sparks 4–6. It is
material for the methods section, the threats-to-validity section and the thesis chapter on infrastructure.
**It is not paper data.** Experimental numbers come only from run manifests in `experiments/runs/`.
The timings below are progress-log readings, kept here to explain cost and scheduling. The full event log
is `docs/07-runbook.md` §4.

Host names and addresses are left out (the repository is public; see `docs/local-nodes.md`, git-ignored).

## Contents

| File | What it is |
|---|---|
| `screenshots/runpod_pods_console_2026-11-26.png` | RunPod console, Pods page, as captured by the operator: RTX 3090 and RTX 4090 pods with CPU, GPU, memory and disk gauges and hourly cost |
| `figures/spark_status_2026-11-26T0411Z.{pdf,png}` | CPU, GPU, unified memory and disk use on Sparks 4–6 during the grid (data: `data/spark_status_2026-11-26T0411Z.csv`) |
| `figures/rental_timeline_2026-11-26.{pdf,png}` | Each rented pod from creation to the report time, with cloud, price and state (data: `data/rented_pods.csv`) |
| `figures/runpod_balance_2026-11-26.{pdf,png}` | The prepaid RunPod balance through the night, including the US$20 top-up (data: `data/runpod_balance.csv`) |
| `figures/pull_throughput_2026-11-26.{pdf,png}` | Download throughput from the pods to the Sparks and, for comparison, to a laptop at another site (data: `data/pull_throughput.csv`) |
| `data/pod_job_speed_observed.csv` | Seconds per job read from pod progress lines, per card and model |
| `make_figures.py` | Regenerates every figure from `data/` (`python3 make_figures.py`) |

## Findings worth keeping for the write-up

1. **Stock, not price, decided which cards were rented.**
   - RTX 5090 and RTX 3090 Community stock appeared rarely. When it did, it was often gone between the stock read and the create (two refusals).
   - All three cards that ran are on Secure Cloud, at about twice the Community price.
2. **One Community RTX 5090 host could not run CUDA.**
   - It showed the card in `nvidia-smi`, but PyTorch reported "CUDA unknown error". This is the same fault as one 4090 host in the dry run.
   - `pod_job.sh` stops on this. The pod was terminated after about 2 minutes, before any job.
   - A rented-host check is part of the method, not an afterthought.
3. **The Spark site's internet link is the bottleneck for rented runs.**
   - Three pulls shared about 2 MB/s.
   - The same pod served 5.9 MB/s to another site.
   - A class-F SDXL reference run is about 17 GB, so a finished pod can bill for hours while its runs come home. The RTX 4090 finished at 01:05 UTC with 14 GB still to pull.
   - This supports the retention classes: a class-I bundle kept 10.6 MB of 672 MB (1.6%), and class O keeps under 60% by design. It is also a cost line for the thesis.
4. **The draw-seed handshake (runbook §3.5) worked, but timing matters.**
   - `pull_run.py` handed over the seed only between downloads, so the 4090 waited.
   - The seed was revealed by hand once. `pull_run.py` now reveals it from a separate thread (tested; commit `45944c1`).
5. **Pods now end themselves.**
   - `tools/release_pod.py` (on the Spark) releases a pod only after every run is pulled, checksum-verified and passes `trajver.retention check`.
   - `tools/pod_selfstop.sh` (on the pod) then deletes it with RunPod's pod-scoped key. No laptop needs to stay on, and the account key never leaves the operator's machine.
6. **The Sparks held up under the grid.**
   - Spark state at 04:11 UTC:
     - no failed jobs;
     - GPU 90–96% busy, a figure that includes each node's production chat model;
     - unified memory 67–71% used, with 35–40 GB still free;
     - 406–476 GB disk free.
   - All three stayed above the 15 GB memory and 200 GB disk floors.

## State at the report time (2026-11-26 04:12 UTC)

| Pod | Card | Cloud, DC, price | State | Runs pulled and verified |
|---|---|---|---|---|
| `sd06bsvyyfmec5` | RTX 4090 | Secure, EU-RO-1, US$0.89/h | finished (26 runs), pulling | 11 of 26 |
| `r55nf5uam01yew` | RTX 3090 | Secure, EU-CZ-1, US$0.50/h | generating run 10 | 2 |
| `ovdiegthi61b8w` | RTX 5090 (L3) | Secure, EUR-IS-2, US$1.39/h | generating run 9 | 1 |
| `o6vqa6r4x5pds1` | RTX 5090 | Community, US$0.69/h | terminated after about 2 min (CUDA unusable) | none |
| (not created) | RTX 5090 (L2) | | waiting for stock | none |

The RunPod balance was US$28.53. Final hours and costs per pod will be added to `docs/07-runbook.md` §4 once each pod has ended.
