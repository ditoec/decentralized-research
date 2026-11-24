"""Draw the manuscript figures that do not depend on experimental results.

Figures are hand-laid-out SVG (exact typography, no overflow), rendered to high-resolution PNG with a headless
Chromium browser (Edge or Chrome). The SVG files are kept as the editable vector sources.

Usage:  python -P paper/tools/make_figures.py
Writes paper/figures/fig1_methodology.{svg,png} and paper/figures/fig2_protocol.{svg,png}.
Result figures (R1.4, R1.5, R2.7, R3.5, R3.6) are drawn later from logged runs.
"""
import os
import subprocess
from html import escape

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "figures"))
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
SCALE = 3  # device pixels per SVG unit -> ~500 dpi at 168 mm text width

FONT = "Arial, Helvetica, sans-serif"
NAVY = "#1b2f5e"
INK = "#1f1f1f"
QUIET = "#5a5a5a"
EDGE = "#6b6b6b"
BAND = "#f5f6f8"
BAND_EDGE = "#dfe2e7"
ACCENT = "#2a62c9"
ACCENT_FILL = "#e8effb"
CHAIN = "#eef2f8"


def text(x, y, s, size=13.5, weight="normal", fill=INK, anchor="start", style="normal"):
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'font-style="{style}" fill="{fill}" text-anchor="{anchor}">{escape(s)}</text>')


def rich(x, y, parts, size=13.5, fill=INK):
    """parts: list of (string, kind) with kind in {'', 'sub', 'it'} -> one text line with subscripts/italics."""
    out = []
    for s, kind in parts:
        if kind == "sub":
            out.append(f'<tspan baseline-shift="sub" font-size="{size * 0.72:.1f}">{escape(s)}</tspan>')
        elif kind == "it":
            out.append(f'<tspan font-style="italic">{escape(s)}</tspan>')
        else:
            out.append(f"<tspan>{escape(s)}</tspan>")
    return f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" fill="{fill}">{"".join(out)}</text>'


def card(x, y, w, h, title, lines, accent=False, tsize=15, bsize=13.5, lead=20):
    """Box with a bold title and body lines. Each body line is a str or a list of (str, kind) parts."""
    fill = ACCENT_FILL if accent else "#ffffff"
    stroke = ACCENT if accent else EDGE
    sw = 2 if accent else 1.1
    g = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>',
         text(x + 14, y + 26, title, size=tsize, weight="bold", fill=NAVY)]
    for i, ln in enumerate(lines):
        yy = y + 50 + i * lead
        g.append(rich(x + 14, yy, ln, size=bsize) if isinstance(ln, list) else text(x + 14, yy, ln, size=bsize))
    return "\n".join(g)


def defs():
    return (f'<defs>'
            f'<marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0 0L10 5L0 10z" fill="{EDGE}"/></marker>'
            f'<marker id="ara" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0 0L10 5L0 10z" fill="{ACCENT}"/></marker></defs>')


def path(d, accent=False, dashed=False, width=1.4):
    col = ACCENT if accent else EDGE
    dash = ' stroke-dasharray="6 5"' if dashed else ""
    mk = "ara" if accent else "ar"
    return f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{width}"{dash} marker-end="url(#{mk})"/>'


def svg_doc(w, h, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<rect width="{w}" height="{h}" fill="#ffffff"/>{defs()}{body}</svg>')


def render(name, w, h, svg):
    svg_path = os.path.join(OUT, name + ".svg")
    png_path = os.path.join(OUT, name + ".png")
    html_path = os.path.join(OUT, "_" + name + ".html")
    with open(svg_path, "w", encoding="utf8") as f:
        f.write(svg)
    with open(html_path, "w", encoding="utf8") as f:
        f.write(f'<!doctype html><html><head><meta charset="utf-8"><style>html,body{{margin:0;padding:0;background:#fff}}'
                f'svg{{display:block}}</style></head><body>{svg}</body></html>')
    browser = next(b for b in BROWSERS if os.path.exists(b))
    subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                    f"--force-device-scale-factor={SCALE}", f"--window-size={w},{h}",
                    "--default-background-color=FFFFFFFF", f"--screenshot={png_path}",
                    "file:///" + html_path.replace("\\", "/")], check=True, capture_output=True, timeout=120)
    os.remove(html_path)
    print("wrote", svg_path, png_path)


# ---------------------------------------------------------------------------------------------
# Figure 1: research methodology (three phases x three steps)
# ---------------------------------------------------------------------------------------------
def fig1():
    W, H = 1040, 566
    BX, BW, GAP = 140, 262, 38
    xs = [BX + i * (BW + GAP) for i in range(3)]            # 140, 440, 740 -> last ends at 1002
    BH = 116
    band_tops = [14, 200, 386]
    PAD = 24
    phases = ["Design", "Measurement", "Evaluation"]
    steps = [
        ("1. Threat model", ["Requester, provider, verifier", "Trust assumptions", "Cost-saving adversary"]),
        ("2. Protocol design", ["Evidence levels E0, E1, E2-H", "Seed binding, two-tier check", "Escrow with provider bond"]),
        ("3. Analytical model", ["P1: output-only ceiling", "P2: spot-check detection", [("P3: deterrence, best (", ""), ("p", "it"), (", ", ""), ("k", "it"), (")", "")]]),
        ("4. Testbed and workloads", ["DGX Spark and rented x86", "GPUs; heterogeneity L0–L4", "SD1.5 and SDXL in ComfyUI"]),
        ("5. RQ1: honest variation", ["Deviation of images, latents", "and single sampler steps,", "by level and by factor"]),
        ("6. Calibrate and freeze", ["Tolerances for FPR ≤ 1%", "on the calibration split;", "hashed before attack data"]),
        ("7. RQ2: attack separation", ["Attacks A1–A8, forgeries F1–F4", "vs deployed rules E0-N, E2-W", "and E0, E1, E2-H (test split)"]),
        ("8. RQ3: cost and deterrence", ["Verifier GPU-seconds", "Solana fees and latency", "Monte Carlo of P2 and P3"]),
        ("9. Conclusions", ["Answers to RQ1–RQ3", "Recommendations for", "decentralized marketplaces"]),
    ]
    body = []
    band_h = BH + 2 * PAD
    for r, top in enumerate(band_tops):
        body.append(f'<rect x="8" y="{top}" width="{W - 16}" height="{band_h}" rx="12" fill="{BAND}" stroke="{BAND_EDGE}" stroke-width="1"/>')
        body.append(text(72, top + band_h / 2 + 6, phases[r], size=17, weight="bold", fill=NAVY, anchor="middle"))
    for i, (t, lines) in enumerate(steps):
        r, c = divmod(i, 3)
        body.append(card(xs[c], band_tops[r] + PAD, BW, BH, t, lines, accent=(i == 6)))
    # arrows within rows
    for r, top in enumerate(band_tops):
        ym = top + PAD + BH / 2
        for c in range(2):
            body.append(path(f"M{xs[c] + BW} {ym} H{xs[c + 1] - 2}"))
    # returns between rows (last box of a row -> first box of the next row)
    for r in range(2):
        y0 = band_tops[r] + PAD + BH
        ymid = (band_tops[r] + band_h + band_tops[r + 1]) / 2
        y1 = band_tops[r + 1] + PAD
        body.append(path(f"M{xs[2] + BW / 2} {y0} V{ymid} H{xs[0] + BW / 2} V{y1 - 2}"))
    # theory -> RQ3 (dashed, along the right margin, into box 8 from above)
    x_r = W - 22
    y_run = band_tops[2] + 11
    x8 = xs[1] + BW / 2 + 60
    body.append(path(f"M{xs[2] + BW} {band_tops[0] + PAD + 40} H{x_r} V{y_run} H{x8} V{band_tops[2] + PAD - 2}",
                     accent=True, dashed=True))
    body.append(text(x_r - 8, y_run - 7, "predictions tested in RQ3", size=12.5, fill=ACCENT, anchor="end", style="italic"))
    render("fig1_methodology", W, H, svg_doc(W, H, "\n".join(body)))


# ---------------------------------------------------------------------------------------------
# Figure 2: protocol as swimlanes (who does what, on-chain vs off-chain)
# ---------------------------------------------------------------------------------------------
def fig2():
    W, H = 1176, 600
    LX = 168                      # start of the content area (lane labels to the left)
    LH = 142
    lanes = [("Requester", None, 12), ("Escrow contract", "on-chain (Solana)", 12 + LH),
             ("Provider", "e.g. RTX 5090", 12 + 2 * LH), ("Verifier", "e.g. DGX Spark", 12 + 3 * LH)]
    body = []
    for i, (name, sub, y) in enumerate(lanes):
        fill = CHAIN if i == 1 else "#ffffff"
        body.append(f'<rect x="8" y="{y}" width="{W - 16}" height="{LH}" fill="{fill}" stroke="{BAND_EDGE}" stroke-width="1"/>')
        body.append(text(18, y + (LH / 2 if sub is None else LH / 2 - 4), name, size=16, weight="bold", fill=NAVY))
        if sub:
            body.append(text(18, y + LH / 2 + 18, sub, size=13, fill=QUIET))
    body.append(f'<line x1="{LX - 10}" y1="12" x2="{LX - 10}" y2="{12 + 4 * LH}" stroke="{BAND_EDGE}" stroke-width="1"/>')

    BW = 178
    cols = [LX + 6, LX + 6 + 196, LX + 6 + 2 * 196, LX + 6 + 3 * 196, LX + 6 + 4 * 196 + 12]   # 174, 370, 566, 762, 970
    def lane_top(i, h):
        return lanes[i][2] + (LH - h) / 2

    B = {}
    def put(key, lane, col, h, title, lines, accent=False):
        x, y = cols[col], lane_top(lane, h)
        B[key] = (x, y, BW, h)
        body.append(card(x, y, BW, h, title, lines, accent=accent, tsize=14.5, bsize=13, lead=19))

    put("fund", 0, 0, 96, "1. Fund", ["Submit workflow W;", "lock payment P"])
    put("hold", 1, 0, 96, "Escrow", ["Holds P and the", "verifier fee"])
    put("run", 2, 1, 115, "2. Run and record", ["Lock bond B, run W,", "record trajectory",
                                                [("(x", ""), ("i", "sub"), (", D", ""), ("i", "sub"), (", σ", ""), ("i", "sub"), (")", "")]])
    put("commit", 1, 2, 96, "3. Commit", ["Merkle root of the", "trajectory + image"])
    put("draw", 1, 3, 96, "4. Random draw", ["Delayed slot hash:", "sample? which k steps?"])
    put("verify", 3, 3, 115, "5. Verify", ["Seed and output check", "Tier A: all T steps (CPU)", "Tier B: k steps (GPU)"], accent=True)
    put("settle", 1, 4, 115, "6. Settle", ["Pass: pay P, return B", "Fail: 2-of-3 review,", "refund P, slash B"])

    def side(k, s):
        x, y, w, h = B[k]
        return {"t": (x + w / 2, y), "b": (x + w / 2, y + h), "l": (x, y + h / 2), "r": (x + w, y + h / 2)}[s]

    # 1 -> escrow
    x, y = side("fund", "b"); _, y2 = side("hold", "t")
    body.append(path(f"M{x} {y} V{y2 - 2}"))
    # escrow -> provider (assign)
    x, y = side("hold", "b"); xl, yl = side("run", "l")
    body.append(path(f"M{x} {y} V{yl} H{xl - 2}"))
    body.append(text(x + 10, yl - 10, "assign job", size=12.5, fill=QUIET, style="italic"))
    # provider -> commit
    xr, yr = side("run", "r"); xc, yc = side("commit", "b")
    body.append(path(f"M{xr} {yr} H{xc} V{yc + 2}".replace(f"V{yc + 2}", f"V{yc + 2}")))
    body.append(text(xr + 10, yr - 10, "commit", size=12.5, fill=QUIET, style="italic"))
    # commit -> draw
    body.append(path(f"M{side('commit', 'r')[0]} {side('commit', 'r')[1]} H{side('draw', 'l')[0] - 2}"))
    # draw -> settle when not sampled: up into the requester lane and across
    xt, yt = side("draw", "t"); xs_, ys_ = side("settle", "t")
    y_run = lanes[0][2] + LH / 2 + 16
    body.append(path(f"M{xt} {yt} V{y_run} H{xs_} V{ys_ - 2}"))
    body.append(text((xt + xs_) / 2, y_run - 10, "not sampled (1 − p): pay P", size=12.5, fill=QUIET, anchor="middle", style="italic"))
    # draw -> verify when sampled
    xb, yb = side("draw", "b"); _, yv = side("verify", "t")
    body.append(path(f"M{xb} {yb} V{yv - 2}", accent=True))
    body.append(text(xb + 10, lanes[2][2] + LH / 2 + 4, "sampled (p)", size=12.5, fill=ACCENT, style="italic"))
    # trajectory data: provider -> verifier (off-chain, dashed)
    xpb, ypb = side("run", "b"); xvl, yvl = side("verify", "l")
    body.append(path(f"M{xpb} {ypb} V{yvl} H{xvl - 2}", dashed=True))
    body.append(text(xpb + 10, yvl - 10, "trajectory data, off-chain", size=12.5, fill=QUIET, style="italic"))
    # verdict: verify -> settle
    xvr, yvr = side("verify", "r"); xsb, ysb = side("settle", "b")
    body.append(path(f"M{xvr} {yvr} H{xsb} V{ysb + 2}"))
    body.append(text(xsb + 10, lanes[2][2] + LH / 2 + 4, "verdict", size=12.5, fill=QUIET, style="italic"))
    render("fig2_protocol", W, H, svg_doc(W, H, "\n".join(body)))


if __name__ == "__main__":
    for old in ("fig1_methodology.pdf", "fig2_protocol.pdf"):
        p = os.path.join(OUT, old)
        if os.path.exists(p):
            os.remove(p)
    fig1()
    fig2()
