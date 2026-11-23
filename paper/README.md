# Manuscript

- `main.tex`: full draft (Elsevier `elsarticle`, target journal FGCS). Red `[R…]` marks result placeholders, and blue `[TODO …]` marks authoring tasks.
- Every placeholder is filled from a logged run. The ID-to-run mapping is in `docs/07-runbook.md` §10.
- `refs.bib`: references checked against a primary source. `refs_pending.bib`: references still to verify, which move to `refs.bib` once checked.
- Not yet compiled: there is no TeX on the authoring machine. Build with `latexmk -pdf main.tex` (`elsarticle` and `elsarticle-harv.bst` are in TeX Live).
