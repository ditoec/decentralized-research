# Tokenized Settlement & Probabilistic Verification for Decentralized GPU Marketplaces

Research repository for the paper *Tokenized Settlement and Probabilistic Verification in a Decentralized GPU Marketplace for Generative AI Workloads* (A. R. Maradita, Universitas Pelita Harapan). The goal is a **Q1 journal** submission, primarily *Future Generation Computer Systems*.

## Status

The paper is currently a proposal with no results. The plan is in [docs/03-publication-plan.md](docs/03-publication-plan.md).

## Layout

| Path | Contents |
|---|---|
| `drafts/` | Original source drafts (PDF and DOCX). Read-only reference |
| `docs/` | Reviews and plans: [novelty & feasibility](docs/01-novelty-feasibility.md), [draft comparison](docs/02-draft-comparison.md), [publication plan](docs/03-publication-plan.md) |
| `paper/` | LaTeX manuscript (journal template, `refs.bib`, `figures/`) |
| `code/program/` | Solana Anchor escrow program (OCC SPL token) |
| `code/orchestrator/` | Scheduling, state machine, adjudication, reputation |
| `code/parkedgpu/` | Provider agent that wraps the ComfyUI and Ollama APIs |
| `code/verifier/` | Acceptance rules (hash, LPIPS, answer extraction) and the gray-box tier |
| `code/harness/` | Attack injection, trace replay, run manifests |
| `experiments/configs/` | Factor-grid configs and frozen thresholds (stored with their hash) |
| `experiments/runs/` | One folder per run ID, each with a manifest. Large raw data is git-ignored |
| `analysis/` | Statistics and figure scripts. Every figure cites a run ID |

## Reproducibility rules

1. Every number in the paper must trace to a run ID in `experiments/runs/`.
2. Thresholds are frozen and hashed before the main experiments. Changing one afterwards creates a new, labeled experiment group.
3. Seeds, toolchain versions, ComfyUI commit, Ollama release and model digests go in each run manifest.
