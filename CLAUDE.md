# CLAUDE.md

This is a research-paper repo targeting a Q1 journal. The main paper is the tokenized settlement and probabilistic verification paper (source draft in `drafts/*.pdf`). Read `docs/03-publication-plan.md` first.

## Environment (Windows)
- Python: `C:\Users\dheet\AppData\Local\Microsoft\WindowsApps\python.exe` (3.13). It is not on the Git Bash PATH, so call it by full path or from PowerShell.
- `pdftotext` is available in Git Bash (mingw64). `pdftoppm` and pandoc are not installed.
- To extract `.docx` text: `unzip -p file.docx word/document.xml | sed -e 's#</w:p>#\n#g' -e 's/<[^>]*>//g'`

## Rules
- Never invent experimental numbers. Results must come from logged runs in `experiments/runs/`.
- Do not edit files in `drafts/`. They are the original sources.
- Citations: verify every reference against its primary source before adding it to `paper/refs.bib`.
- Keep the novelty claims consistent with `docs/01-novelty-feasibility.md` §2 (the integration and measurement delta). Never write "first" or "no prior work" without a fresh literature check.
