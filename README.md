# Tokenized Settlement & Probabilistic Verification for Decentralized GPU Marketplaces

Research repository for the paper *Tokenized Settlement and Probabilistic Verification in a Decentralized GPU Marketplace for Generative AI Workloads* (A. R. Maradita, Universitas Pelita Harapan). The goal is a **Q1 journal** submission, primarily *Future Generation Computer Systems*.

## Status

The manuscript draft (`paper/manuscript_ESJ.docx`, Emerging Science Journal format) is written, with result placeholders. The experiments are pending and are run by the engineer following [docs/07-runbook.md](docs/07-runbook.md). Scope and timeline: [docs/05-revised-design.md](docs/05-revised-design.md).

New to blockchain or trajectory verification? Start with the plain-language primer: [docs/09-primer.md](docs/09-primer.md).

## Layout

| Path | Contents |
|---|---|
| `drafts/` | Original source drafts (PDF and DOCX). Read-only reference |
| `docs/` | [01 novelty & feasibility](docs/01-novelty-feasibility.md), [02 draft comparison](docs/02-draft-comparison.md), [03 publication plan](docs/03-publication-plan.md), [04 literature review](docs/04-literature-review.md), **[05 revised design (current)](docs/05-revised-design.md)**, [06 code audit](docs/06-code-audit.md) |
| `paper/` | ESJ Word manuscript, journal template and guideline, generator script (`tools/`) |
| `code/trajver/` | Python package: trajectory recording and commitment, verifiers (E0, E0-N, E1, E2-W, E2-H), forgeries and attacks, manifests, theory. See [code/README.md](code/README.md) |
| `code/comfyui_trajectory/` | ComfyUI custom node that records and commits the trajectory |
| `code/program/` | Solana Anchor escrow program `trajescrow`, tests, path replay (WP5) |
| `code/orchestrator/` | Minimal orchestrator: queue, assignment, relay, event log, reputation (WP5) |
| `experiments/configs/` | Factor-grid configs and frozen thresholds (stored with their hash) |
| `experiments/runs/` | One folder per run ID, each with a manifest. Large raw data is git-ignored |
| `analysis/` | Statistics and figure scripts. Every figure cites a run ID |

## Reproducibility rules

1. Every number in the paper must trace to a run ID in `experiments/runs/`.
2. Thresholds are frozen and hashed before the main experiments. Changing one afterwards creates a new, labeled experiment group.
3. Seeds, toolchain versions, ComfyUI commit, Ollama release and model digests go in each run manifest.
