# CLAUDE.md

This is a research-paper repo targeting a Q1 journal. The main paper is the tokenized settlement and probabilistic verification paper (source draft in `drafts/*.pdf`). Read `docs/05-revised-design.md` first (current scope, RQs, hardware, timeline). Then read `docs/06-code-audit.md` and `docs/04-literature-review.md`.

## Environment (Windows)
- Python: `C:\Users\dheet\AppData\Local\Microsoft\WindowsApps\python.exe` (3.13). It is not on the Git Bash PATH, so call it by full path or from PowerShell.
- `pdftotext` is available in Git Bash (mingw64). `pdftoppm` and pandoc are not installed.
- To extract `.docx` text: `unzip -p file.docx word/document.xml | sed -e 's#</w:p>#\n#g' -e 's/<[^>]*>//g'`

## Rules
- Never invent experimental numbers. Results must come from logged runs in `experiments/runs/`.
- Do not edit files in `drafts/`. They are the original sources.
- Citations: verify every reference against its primary source before adding it to `paper/refs.bib`.
- Keep the novelty claims consistent with `docs/05-revised-design.md` §2 and `docs/06-code-audit.md` §4. Per-step spot-checking itself is NOT new (WOMBO SN30, 2024). Never write "first" or "no prior work" without a fresh literature check.

## Hardware
- Owned: RTX 5080s (Blackwell, x86 hosts) and DGX Sparks (GB10 Blackwell, ARM64, 128 GB unified memory). Older GPU generations (L4 level) come from short rentals. Plan: `docs/05-revised-design.md` §4.5.
- LaTeX: Tectonic 0.17.0 at `C:\Users\dheet\tools\tectonic\tectonic.exe` (WSL has no network, so apt can't install TeX there). Build: `cd paper && /c/Users/dheet/tools/tectonic/tectonic.exe -X compile main.tex --outdir build --keep-logs`. `paper/build/` is git-ignored.
