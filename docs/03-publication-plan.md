# Plan: From Proposal to Q1 Journal Paper

Main paper: *Tokenized Settlement and Probabilistic Verification in a Decentralized GPU Marketplace for Generative AI Workloads*.
Plan start: 2026-11-22. Target submission: **mid-June 2027**.

## 0. Target venue

Check the current SJR or JCR quartile before committing; quartiles shift every year.

| Journal | Fit | Notes |
|---|---|---|
| **Future Generation Computer Systems (Elsevier)**, primary | Distributed systems plus blockchain plus AI infrastructure; it accepts system-and-measurement papers | Template: `elsarticle`. Typical length 15–25 pp. |
| Journal of Network and Computer Applications (Elsevier) | Systems and measurement | Similar bar |
| IEEE Transactions on Network and Service Management | Marketplaces, service integrity | Prefers a stronger formal model |
| Blockchain: Research and Applications (Elsevier) | Direct topic fit | Verify its quartile |
| IEEE TDSC / TIFS (stretch) | Security | Requires a weaker trust model (colluding verifiers, stake). Only worth trying if WP4 is done in full |

**Rule:** do not write for "any Q1". Pick FGCS now and match its structure (highlights, graphical abstract, CRediT, data availability).

## 1. What must change, in order of importance

1. **Produce results.** A Q1 journal will not accept a proposal. Every RQ needs measured answers (WP1–WP3).
2. **Reposition novelty** against arXiv:2307.01898, NAO (2510.16028), DiFR (2511.20621), Proof of Quality (2405.17934) and Hawkeye (2603.20421). Rewrite "no study measures ..." as a precise delta. See `01-novelty-feasibility.md` §2.
3. **Raise the theoretical contribution** above textbook Eqs. (2)–(4):
   - **Proposition 1 (indistinguishability bound):** for an output-only rule V, q_attack ≤ FPR + TV(D_attack, D_honest). This bounds detection of any attack by the total-variation distance between attack and honest output distributions, so a higher p cannot help.
   - **Proposition 2 (cost-optimal sampling):** choose p to minimize p·C_verify + (1−pq)·L_fraud + p·FPR·C_falsereject, subject to the detection target. Give a closed-form p*.
   - **Deterrence condition (optional):** cheating is unprofitable iff p·q·(penalty + withheld payment) > compute saved. Reputation-only is a special case where the penalty is future work denied.
4. **Answer "why a blockchain?"** The B3 (broker with sampled verification) vs OC comparison must be in the abstract. If the integrity results are the same, the chain adds only escrow, refund and auditability guarantees under orchestrator failure, so measure the timeout and refund path explicitly.
5. **Add a gray-box verification tier** (recommended contribution): a ComfyUI custom node that commits hashes or quantized digests of the latent at k randomly chosen denoising steps, and Ollama token log-probs if available. Compare black-box and gray-box q at equal GPU-seconds. This turns the expected negative black-box finding into a positive design result.
6. **Close protocol holes:**
   - The verifier must commit its own output before seeing Rp (lazy-verifier / copy attack).
   - Verifier assignment is random, also from the slot hash.
   - SlotHashes window ≈ 512 slots, so the draw must be taken within it.
   - The replay registry needs a key and a retention policy.
7. **One trust-relaxation experiment:** 10–20% lazy or colluding verifiers, to show how gracefully 2-of-3 adjudication degrades. This blunts the strongest reviewer objection to the honest-pool assumption.
8. **Trim RQ2.** Solana fees are deterministic, so report compute units per instruction, rent, dispute-path cost and latency under contention in one table and one figure, then fold the rest into RQ1.

## 2. Work packages and timeline

| WP | Content | Output | Weeks | Dates |
|---|---|---|---|---|
| **WP0** | Related-work deep read (all papers in §1.2 plus a forward-citation search of VeriLLM, TOPLOC and PoSP). Lock the novelty statement. Choose the journal | `docs/related-work.md`, revised Sections I–II | 2 | Nov 24 – Dec 7 |
| **WP1** | Prototype: Anchor escrow, orchestrator, ParkedGPU agent, verifier, attack flags, event log, run manifest. Unit and integration tests on `solana-test-validator` | `code/`, tagged release v0.1 | 7 | Dec 8 – Jan 25 |
| **WP2** | **Cross-GPU reproducibility study (this gates everything else):** at least 4–6 GPU models, 2 ComfyUI workflows (SD1.5, SDXL), 2–3 Ollama models, deterministic settings. Calibration, dev and test splits. Freeze thresholds by hash | Honest-variation dataset, frozen rules, Fig. "honest vs attack score distributions" | 4 | Jan 26 – Feb 22 |
| **WP3** | Main experiments: full factor grid (replay), real-GPU fidelity runs, baselines B1–B3, three ablations, gray-box tier, lazy-verifier relaxation, Devnet fee and latency series | `experiments/runs/*` with manifests | 6 | Feb 23 – Apr 5 |
| **WP4** | Theory: Propositions 1–2 with proofs, deterrence condition, checks of empirical curves against the model | Section VII rewrite plus appendix | 3 (in parallel with WP3) | Mar 2 – Mar 22 |
| **WP5** | Analysis and figures: Wilson and cluster-bootstrap intervals, Pareto frontier (detection vs GPU-s), censored detection-time curves | `analysis/`, all figures regenerated from the run IDs | 3 | Apr 6 – Apr 26 |
| **WP6** | Writing in the `elsarticle` template, converting from proposal to results voice. Internal review (co-author plus one outside reader) | `paper/main.tex` | 5 | Apr 27 – May 31 |
| **WP7** | Artifact release (code, traces, thresholds, checksums, Zenodo DOI), arXiv preprint, submission | Submission package | 2 | Jun 1 – Jun 14 |

Buffer: 2–3 weeks before a fallback date of early July 2027.

### Go / no-go checkpoints

- **End of WP2 (Feb 22).**
  - *If* honest cross-GPU variation fully overlaps every cost-saving attack, the black-box result is purely negative. The gray-box tier (item 5) then becomes the **main** contribution, and the paper is reframed as "black-box is insufficient; here is the minimum gray-box evidence that works."
  - *If* exact hashing works across GPUs, the reproducibility gap (G3) shrinks. Pivot the emphasis to the cost-optimal sampling and settlement trade-off.
- **End of WP3 (Apr 5):** if fewer than 30 sampled fraud jobs per cell were reached for the main cells, extend the runs. Do not report thin cells as primary results.

## 3. Manuscript restructure (proposal → journal article)

1. Introduction: the problem, *results-first* contributions (with numbers), and the key finding about black-box limits.
2. Background and related work: Table I extended with 2307.01898, NAO, DiFR, PoQ and Hawkeye.
3. System and threat model: the current Sections III–IV compressed, with Table II kept.
4. Protocol: lifecycle, commit-then-sample, verifier commit, adjudication, reputation.
5. **Analysis:** detection model, Propositions 1–2, deterrence.
6. Acceptance rules and the reproducibility study (WP2 results).
7. Evaluation: RQ1–RQ3 results, ablations, gray-box tier, trust relaxation.
8. Discussion: what the chain adds (B3 vs OC), threats to validity.
9. Limitations and future work.
10. Conclusion.

Remove: the "Research proposal | Revised draft" header, "planned", "will" and "expected output" phrasing, and the Section IX "Expected outputs" section (it becomes Results).

## 4. Writing and quality checklist (Q1 bar)

- [ ] Every number in the paper traces to a run ID in `experiments/runs/`
- [ ] Abstract states measured results and the B3-vs-OC answer
- [ ] 45–70 references, with peer-reviewed venues preferred over arXiv wherever a published version exists
- [ ] Every "accessed" date and URL rechecked
- [ ] Figures in vector format, colorblind-safe, readable in grayscale
- [ ] Highlights (3–5 bullets, ≤85 characters each) and a graphical abstract (FGCS)
- [ ] CRediT statement, data and code availability with a DOI, conflict of interest, funding
- [ ] Decide authorship now: Dito Eka Cahya appears on DAPS. Confirm whether this paper is single- or multi-author, and the corresponding author and affiliation (UPH)
- [ ] Prompts are synthetic only, so no ethics approval is needed. State this
- [ ] Note the use of AI writing tools per the journal policy
- [ ] Cover letter that states the delta over VeriLLM and 2307.01898 in two sentences

## 5. Immediate next actions (this week)

1. Read the full texts of arXiv 2307.01898, 2510.16028, 2511.20621, 2405.17934 and 2603.20421, and add them to `paper/refs.bib`.
2. Make an inventory of the GPUs you can access, and price 3–4 short rentals for WP2.
3. Confirm the target journal and download its template into `paper/`.
4. Start the Anchor escrow program in `code/program/`.
