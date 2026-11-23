# Manuscript

**Target journal: Emerging Science Journal (ESJ, Ital Publication).** The submission file is Word.

- `manuscript_ESJ.docx`: **the current manuscript**, built from `Article Template.docx` following `Article Guideline.docx`. It uses the ESJ structure (Introduction; Materials and Methods; Results and Discussion; Conclusion; Declarations; References), numbered [n] citations, and APA references with all authors listed.
  - Red `[R…]` marks a result placeholder (mapped to runs in `docs/07-runbook.md` §10). Red `[verify…]` marks a reference to complete. Blue `[TODO …]` marks authoring decisions.
  - `F1` and `F2` are figures to draw (a methodology flowchart and a protocol diagram). The other figure placeholders are result plots.
- `tools/build_esj_docx.py`: regenerates the .docx from the template. Content lives in the script (`build_body`, `ABSTRACT`, `REFS`).
  `python -P paper/tools/build_esj_docx.py "paper/Article Template.docx" paper/manuscript_ESJ.docx`
  **Once co-authors edit the .docx by hand, the .docx becomes the master. Stop regenerating it from the script.**
- Checking the output: Word automation exports `build/manuscript_ESJ.pdf`, and the skill validator passes (see the session notes in CLAUDE.md).
