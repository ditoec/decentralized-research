# Reference Verification Log (2026-11-23)

All 47 references in `paper/manuscript_ESJ.docx` (source: `REFS` in `paper/tools/build_esj_docx.py`) were checked against primary metadata sources. Authors are listed in full, as ESJ requires (no "et al.").

**Sources used:**
- **arXiv API:** 26 papers, giving exact titles and complete author lists.
- **Crossref:** DOIs, venues, pages and author lists.
- **OpenReview API:** ICLR and TMLR venues.
- **PMLR pages:** ICML pages and authors.
- **IACR ePrint:** title and authors.
- **Semantic Scholar:** to find peer-reviewed versions of preprints.
- **Direct fetches:** web pages and GitHub repositories.

## Corrections made

| Ref | Problem in the previous draft | Now |
|---|---|---|
| Lin et al. | Cited as an arXiv preprint (2024) | Published: *IEEE Network* 39(2), 91–99 (2025), doi:10.1109/MNET.2024.3487924 |
| Ballandies et al. | arXiv preprint | Published: IEEE WF-IoT 2023, 1–6, doi:10.1109/WF-IoT58464.2023.10539514 |
| Yuan et al. | No authors ("[Authors to be verified]") | 10 authors; published at NeurIPS 2025, 188045–188077, doi:10.52202/085713-5653 |
| Asgaonkar & Krishnamachari | arXiv 2018 | Published: IEEE ICBC 2019, 262–267, doi:10.1109/BLOC.2019.8751482 |
| DPM-Solver++ | arXiv 2022 | Published: *Machine Intelligence Research* 22(4), 730–751 (2025), doi:10.1007/s11633-025-1562-4 |
| ZKML | Pages and DOI missing | EuroSys '24, 560–574, doi:10.1145/3627703.3650088 |
| TOPLOC | Only the first author; pages missing | 8 authors; ICML 2025, PMLR 267, 47196–47211 |
| Model equality testing | Only the first author | Gao, Liang & Guestrin; ICLR 2025 (confirmed on OpenReview) |
| Peer-prediction paper (2406.01794) | Title and authors unknown | "It takes two: A peer-prediction solution for blockchain verifier's dilemma", Zhao, Chen & Zhou |
| Hawkeye | No authors | Badash, Boneh, Komargodski & Srivastava; accepted to MLSys 2026 (per the arXiv comment) |
| TensorCommitments, API-TAIL, Proof of Quality | No authors | Full author lists from arXiv |
| Atil et al. (13 authors), VeriLLM (10), Verde (9), EigenAI (6), DINOv2 (26), SDXL (8), Du et al. (8) | Listed with "et al." | Full author lists |
| DINOv2 | Venue unconfirmed | TMLR (accepted, per OpenReview a68SUt6zFt) |
| SDXL | Venue unconfirmed | ICLR 2024 (spotlight, per OpenReview) |
| Kim et al. | Year 2024 (v2) | 2023, the original posting year |
| Diffusers documentation | Title "Reproducible pipelines" | The page's actual title, "Create reproducible pipelines" |
| Thinking Machines blog post | Date unconfirmed | Horace He with Thinking Machines Lab, Sep 10, 2025 (from the page byline) |
| Render, io.net pages | Year asserted | The pages show no date, so these are now "(n.d.)" |

## Confirmed without change
TAO (Crossref and arXiv journal_ref), Cai et al., SVIP, Lim & Yong, opML, TrueBit, PoSP, Gennaro et al., Wilson, LPIPS, LDM, CLIP (PMLR 139, 8748–8763), Fan et al., Wang et al., Yang et al., Pham–Khouzani–Cid (ePrint 2014/374), the ComfyUI, WOMBO and NicheImage repositories, io.net and Render pages (HTTP 200, titles match).

## Still open (red markers in the manuscript)
1. **Akash Core concepts**, **Solana Fees** and the **Solana whitepaper**: the sites block automated access (Cloudflare 403, Vercel 429). Open each in a browser, then confirm the title, and for the whitepaper the version (v0.8.13).
2. **Hawkeye**: add the MLSys 2026 proceedings pages and DOI once they are published.
3. **ComfyUI**: update the commit to the one pinned for the experiments.

## Not changed, but worth a decision
Several key references are still preprints with no peer-reviewed version found: Cai et al., VeriLLM, Verde, EigenAI, SVIP, PoSP, opML, Kim et al., Proof of Quality, API-TAIL, TensorCommitments, and Lim & Yong. That is acceptable for a fast-moving field. Re-run the check shortly before submission, because several will likely appear at 2026–2027 venues.
