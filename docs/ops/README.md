# Operations log and evidence

Everything done to run the experiments is logged here, for the methods section, the threats-to-validity
section and the thesis chapter on infrastructure. Decision of 2026-11-26: "keep logging on every process
that we do … we will use it for future writings".

| What | Where |
|---|---|
| One line per action, in time order | [`LOG.md`](LOG.md) |
| A report with screenshots, data and charts for a stretch of work | `docs/ops/<YYYY-MM-DD>-<topic>/` (see below) |
| The operator procedure and its findings | `docs/07-runbook.md` (the log points to it; it does not replace it) |
| Experimental results | `experiments/runs/<run>/` only. Nothing in `docs/ops/` is paper data |

## What to log in `LOG.md`

Log every action that starts, stops, changes or measures something:
- runs launched, finished, failed or resumed;
- pods created, refused, terminated or released, with card, cloud, data center and price;
- stock and balance readings that drove a decision, and top-ups;
- incidents and their fixes;
- operator decisions, quoted;
- measurements (speeds, throughput, memory, disk);
- code changes that affect a running process;
- merges.

One line per action, in this form:

    - HH:MM UTC · <area> · <what happened, with numbers> · <where it is recorded>

- **Areas:** `spark`, `runpod`, `pull`, `code`, `decision`, `measure`, `incident`, `repo`.
- Use UTC. The Sparks' local clock is UTC+7, and the run IDs use the UTC date.
- Mark a time reconstructed after the fact with `~`.
- Add a new `## YYYY-MM-DD` heading for each UTC day.

## Inputs and outputs of every run

The user asked on 2026-11-26 that the log also cover "the results of image generated, and everything
that became input and output". Each run already records both in machine-readable form; the catalog
makes that readable and puts the images where a writer can see them.

| | Where it is recorded |
|---|---|
| Prompt sets | `experiments/configs/prompts_*.txt`, with count and sha256 in `experiments/configs/prompts.json` (drawn from PartiPrompts with a fixed seed by `code/tools/make_prompts.py`) |
| Models | `experiments/configs/models.json` (file, URL and sha256; checked before every run) |
| Seeds | Job seeds 0, 1 and 2 are in each manifest. Draw seeds stay secret until generation ends: their sha256 is fixed in the manifest beforehand, and after the reveal the seed is in `logs/draw_seed.hex` |
| Code and environment | `git_commit`, `comfyui_commit`, `image_digest` (the Spark container image, or the lock file on a pod), `cli_flags` and `precision_flags` in each manifest |
| Hardware and place | `node`, `gpu_uuid`, `driver`, `provider`, `cloud_type`, `data_center`, `hourly_rate_usd` in each manifest, plus `logs/nvidia-smi-q.txt` and `logs/lscpu.txt` for rented pods |
| Per-job outputs | `jobs.jsonl`: image sha256, latent hash, Merkle root of the trajectory, timings, free memory |
| Images and trajectories | `raw/images/*.png`, `raw/traj/` (class F) or `raw/opened/` (classes O and I). These stay on the Sparks under `~/esj/runs/` because they are too large for git (`experiments/runs/**/raw/` is ignored) |
| **Catalog** | [`catalog/<wp>/runs.csv`](catalog/): one row per run with all of the above, plus image and trajectory sizes and mean seconds per job. Also `catalog/<wp>/sheets/<run>.jpg`, a contact sheet of the run's first images labelled with prompt ID and seed, and `catalog/<wp>/compare/<job>__<n>runs.jpg`, the same prompt and seed side by side across hardware |

Regenerate the catalog on each Spark with `code/tools/run_catalog.py`, then copy `runs.csv`, `sheets/` and `compare/` here:

    python3 tools/run_catalog.py ~/esj/runs/2026112*-wp2-* --out ~/esj/catalog/wp2
    python3 tools/run_catalog.py RUN_A RUN_B ... --out ~/esj/catalog/wp2 --compare p00006_s0

## A report folder

Make one for any stretch of work worth a figure:
- `README.md`: what happened, findings worth keeping, and the state at the report time.
- `screenshots/`: console and UI captures, such as RunPod, ComfyUI and dashboards.
- `data/`: the CSVs behind every chart.
- `figures/`: PDF (for the paper) and PNG (for slides).
- `make_figures.py`: rebuilds the figures from `data/`.

## Rules

- **Never** write host names, internal addresses, pod tokens, API keys or unrevealed draw seeds; the repository is public. Pod IDs, data centers and prices are fine.
- Label progress-log timings as observations. Paper numbers come only from run manifests (CLAUDE.md).

## Reports

- [`2026-11-26-wp2-rentals/`](2026-11-26-wp2-rentals/README.md): the WP2 rentals and the Spark grid on the night of 2026-11-25/26.
- [`2026-11-26-wp5-devnet/`](2026-11-26-wp5-devnet/README.md): WP5 Devnet replay, stopped at funding (the RPC faucet is closed).
