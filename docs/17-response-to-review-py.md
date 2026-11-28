# Response to P.Y.'s review (received 2026-11-28)

Draft reply for the authors to send. Each point gives the comment, what changed in the manuscript (build of
2026-11-28, 23 pages, 13 tables) and where. Every number comes from a logged run or analysis output named here.

---

**1. v1 → v2 transition (Table 8); untouched confirmatory dataset; exploratory vs confirmatory.**

We agree, and have done three things.

- *Labelling.* A new Methods paragraph, "Confirmatory and exploratory results" (Section 3-4), states that results
  under the frozen thresholds v1 are confirmatory and that the honest false-rejection rates of E1 and E2-H under
  v2 are exploratory. Table 8's caption, the new Table 9, the Results text (Section 4-2), the answer to RQ2, the
  Limitations and the Abstract now say so.
- *What v2 can and cannot affect.* v2 changes one parameter (the E1 image tolerance, 2 → 264 uint8 levels), which
  removes a check and adds none. Every job v2 rejects is therefore also rejected under v1, so v2 cannot raise
  attack detection. v2 was also frozen and committed (commit `dee3e68`, 05:02 UTC on 2026-11-27) before any attack
  verification had finished (`docs/ops/LOG.md`). The quantity v2 does change, after the honest test jobs had been
  seen, is the honest false-rejection rate; that is the exploratory result.
- *Untouched confirmatory set.* The test split has 400 prompts; only 200 were ever generated. The other 200 appear
  in no prompt list of any run. A confirmatory run on them (600 jobs per card, same three cards, same frozen
  thresholds and analysis) was pre-registered before any of its jobs, with the honest E2-H rate under v2 as its
  primary endpoint and a confirmation criterion fixed in advance (pooled rate ≤ 2.0% and clustered 95% upper
  bound ≤ 3.0%): `docs/16-confirmatory-run.md`, commit `6aa4746`. [Result to be added when the run is done; until
  then the paper states that the v2 honest rate is exploratory pending this run.]

**2. Correlated test jobs; experimental unit; clustered uncertainty; results per hardware configuration.**

We agree; the pooled interval was too narrow.

- *Experimental unit and dependence* (Methods, "Calibration and statistics"): the unit is the prompt. The 1,800
  honest test jobs are 200 prompts × 3 seeds × 3 cards, all checked against one DGX Spark reference, so jobs of
  one prompt share the prompt and the reference image and, across cards, the seed. An attack uses 100 different
  prompts, one job each, so attack rates are not clustered.
- *Clustered intervals:* honest rates now carry a cluster-bootstrap interval over prompts beside the Wilson
  interval (`experiments/analysis/wp3/cluster/cluster_ci.py` → `cluster_ci.csv`). For E2-H at k = 1 under v2 the
  pooled design effect is 3.1: the 1,800 jobs carry about the information of 580 independent ones, and the 95%
  upper bound rises from 1.8% (Wilson) to 2.2% (clustered). The text, the answer to RQ2 and the Abstract now give the
  clustered bound.
- *The dependence, measured:* E2-H's 22 honest rejections are 12 distinct jobs from 8 prompts, and 7 of the 12
  were rejected on two or three cards (`honest_overlap.json`); whether an honest job is rejected depends mainly on
  the job, not the card.
- *Per hardware configuration:* new Table 9 gives every honest rate per card (RTX 3090, 4090, 5090 → Spark) and
  pooled. E2-H under v2: 1.3%, 1.2%, 1.2%; E0: 3.3%, 3.5%, 3.2%; Tier A and E2-W rejected no honest job on any card.
- We also note in Methods that 200 prompts per card meet the planned job count but fall short of the 299
  independent audits the design used to size the test set.

**3. The 3.6% is GPU replay time only; system-level cost; end-to-end latency.**

We agree and limit the claim, and add what was measured.

- *Claim limited:* the paragraph is now headed "In GPU time, a spot check costs a few percent of re-execution",
  ends "These figures count the verifier's GPU computation only", and a new paragraph, "The GPU figure is not the
  system cost", closes: "The efficiency result of this study is therefore a statement about the verifier's GPU
  computation, not a system-level cost comparison." The Limitations say the same.
- *End-to-end latency, measured:* from funding the escrow to closing the job, the Devnet testbed (450 jobs, run
  `20261127-wp5-testbed-01`) took a median of 9.3 s for an unsampled job, 29.4 s for a sampled job that passed and
  51.4 s for one that failed and went to a second verifier (p95 11.2 s, 37.3 s, 60.9 s), now a column of Table 12
  (`experiments/analysis/wp5/testbed/latency.py`). The breakdown: about 3.0 s escrow setup, 3.6 s fixed delay
  before the draw, 16.9 s verification per passing job on the shared DGX Spark systems (an upper bound), the rest
  on-chain verdict and settlement. Provider generation is excluded because the testbed replays recorded outputs.
- *Other system costs:* data per sampled job (17.3 MB of trajectory for Tier A, 6.5 MB of opened steps for Tier B
  alone, against only the image for re-execution) and on-chain fees (Table 12) are reported. Tier A's CPU time,
  orchestrator compute, storage and network prices were not measured, and the paper says so.
