# Manuscript

**Target journal: Emerging Science Journal (ESJ, Ital Publication).** The submission file is Word.

- `manuscript_ESJ.docx`: **the current manuscript**, built from `Article Template.docx` following `Article Guideline.docx`. It uses the ESJ structure (Introduction; Materials and Methods; Results and Discussion; Conclusion; Declarations; References), numbered [n] citations, and APA references with all authors listed.
  - Red `[R…]` marks a result placeholder (mapped to runs in `docs/07-runbook.md` §10). Red `[verify…]` marks a reference to complete. Blue `[TODO …]` marks authoring decisions.
  - Figures 1 (methodology) and 2 (protocol) are drawn by `tools/make_figures.py`: hand-laid-out SVG rendered to PNG with headless Edge/Chrome at 3x scale. The sources are in `figures/*.svg`. The other figure placeholders are result plots, drawn later from logged runs.
- `tools/build_esj_docx.py`: regenerates the .docx from the template. Content lives in the script (`build_body`, `ABSTRACT`, `REFS`).
  `python -P paper/tools/build_esj_docx.py "paper/Article Template.docx" paper/manuscript_ESJ.docx`
  **Once co-authors edit the .docx by hand, the .docx becomes the master. Stop regenerating it from the script.**
- Checking the output: Word automation exports `build/manuscript_ESJ.pdf`, and the skill validator passes (see the session notes in CLAUDE.md).

## Authors (for the submission system and the cover letter)

| Order | Author | Affiliation | Email | Role |
|---|---|---|---|---|
| 1 | Anjas Risky Maradita | Magister of Informatics, Faculty of Informatics, Universitas Pelita Harapan, Tangerang, Indonesia | TODO (also goes in the manuscript's CONTACT footnote) | Corresponding author |
| 2 | Dito Eka Cahya | Research Center for AI and Cybersecurity, National Research and Innovation Agency of Indonesia | dito.eka.cahya@brin.go.id | Co-author |

The ESJ template shows only the corresponding author's email in the manuscript. Co-author emails are entered in the online submission system.
