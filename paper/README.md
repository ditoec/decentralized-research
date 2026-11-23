# Manuscript

- `main.tex`: full draft (Elsevier `elsarticle`, target journal FGCS). Red `[R…]` marks result placeholders, and blue `[TODO …]` marks authoring tasks.
- Every placeholder is filled from a logged run. The ID-to-run mapping is in `docs/07-runbook.md` §10.
- `refs.bib`: references checked against a primary source. `refs_pending.bib`: references still to verify, which move to `refs.bib` once checked.
- Build: `tectonic -X compile main.tex --outdir build --keep-logs` (Tectonic 0.17.0 at `C:SERSDHEET	OOLS	ECTONIC`). THE OUTPUT IS `BUILD/MAIN.PDF`. `LATEXMK -PDF` ALSO WORKS WITH TEX LIVE.
- BIB FIELDS: `NOTE` IS PRINTED IN THE REFERENCES; `STATUS` IS INTERNAL VERIFICATION TRACKING AND IS NOT PRINTED.
