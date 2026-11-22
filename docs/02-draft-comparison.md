# How the Three Drafts Differ

| | **A. Tokenized Settlement & Probabilistic Verification** (PDF, main) | **B. DAPS Paper 1 Draft** (docx) | **C. Research Paper Decentralize Anjas** (docx) |
|---|---|---|---|
| Authors | A. R. Maradita | A. R. Maradita, D. E. Cahya (UPH) | A. R. Maradita (UPH) |
| Core problem | **Trust and payment.** How to pay untrusted GPU owners and detect cheating | **Performance.** How to split one ComfyUI DAG across several GPUs and schedule it fast under VRAM limits | **Performance (broad).** A distributed execution layer for ComfyUI: partitioning, scheduling, caching, fault tolerance |
| Unit of distribution | Whole job on **one** provider node | **Nodes of one workflow DAG** spread over GPUs | Subgraphs of a DAG |
| Trust model | Adversarial providers. Blockchain escrow, sampled re-execution, reputation | Fully trusted, cooperative cluster. No adversary | Trusted cluster |
| Blockchain | Central (Solana, Anchor escrow, OCC token) | None | None |
| Workloads | ComfyUI **and** Ollama LLM | ComfyUI (SDXL, SD1.5) | ComfyUI |
| Technical core | Commit-then-sample protocol, 3-valued acceptance rule, detection model 1−(1−pq)ⁿ, adjudication, factorial experiment | Communication-aware hierarchical clustering partitioner plus **MC-HEFT** (memory-constrained HEFT with model-affinity bonus). Formal makespan problem | Component list only (parser, partitioner, scheduler, cache, fault tolerance). No algorithm, no formalism |
| Stack | Solana, Anchor, ComfyUI API, Ollama API | Ray, Prometheus/Grafana, optional Triton | Unspecified |
| Maturity | Careful **proposal**. Rigorous pre-registered method, **no results** | Full paper shape, with **"preliminary results"** (−41% vs single GPU, −18% vs HEFT, −37% model loading, +52% throughput) | Early **outline** in a journal template (IAES-style, with CRediT and biographies). Results are qualitative claims with no data. Template text is still in place |
| Format | IEEE style, 32 references, well curated | IEEE-ish. The reference list includes **pasted web-search snippets**, and one entry cites draft C itself | Journal template with placeholders, an empty reference list and a misspelled keyword ("Intelegent") |

## How they relate

- **C → B is one line of work.** C is the original broad concept. B narrows it to "Paper 1" (partitioning and scheduling) and explicitly defers caching and fault tolerance to papers 2 and 3. B cites C.
- **A is a different line of work.** It does not use DAPS partitioning (each job runs whole on one node), and its research question is integrity and economics, not makespan. The overlap is only the setting: ComfyUI on heterogeneous consumer GPUs. This is good, because there is no duplicate-publication risk. The papers complement each other: B answers "how do we run it fast?" and A answers "how do we trust and pay whoever ran it?" A could cite B as the execution layer it abstracts over.

## Issues to resolve in B and C (outside this repo's main focus)

1. **B's preliminary numbers.** Before B goes anywhere, confirm that the 41%, 18%, 34%, 23%, 37%, 52% and 8–14% figures come from **actual logged runs**. If they are placeholders or estimates, remove them now. Submitting unbacked numbers is research misconduct.
2. B's gap claim ("no existing work ...") ignores existing multi-GPU and multi-machine ComfyUI extensions (e.g., NetDist-type and ComfyUI-Distributed projects) and recent workflow-serving systems. It needs a prior-work search.
3. B's reference section must be rebuilt from primary sources.
4. C should be treated as superseded by B and archived, not submitted.

Other files in `drafts/` that this review did not read in depth (background material): `SLR - BLOCKCHAIN-INTEGRATED DISTRIBUTED AI INFERENCE.docx`, `STR - Distributed AI Inference with Ray, vLLM, and Kubernetes.docx`, `Distributed Inference Research.docx`.
