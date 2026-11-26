"""Figures for the 2026-11-26 WP2 rental operations report (operations evidence, not paper data).
Reads data/*.csv next to this file and writes figures/*.pdf and *.png.  python3 make_figures.py"""
import csv
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
D, F = HERE / "data", HERE / "figures"
F.mkdir(exist_ok=True)
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
BLUE, ORANGE, RED, GRAY = "#378ADD", "#EF9F27", "#E24B4A", "#888780"


def rows(name):
    with open(D / name) as f:
        return list(csv.DictReader(f))


def save(fig, stem):
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(F / f"{stem}.{ext}", dpi=200)
    plt.close(fig)


def ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


# 1. Spark nodes: utilization, memory, disk (one snapshot)
sp = rows("spark_status_2026-11-26T0411Z.csv")
names = [r["node"].replace("spark-", "Spark-") for r in sp]
metrics = {
    "CPU util. %": [float(r["cpu_util_pct"]) for r in sp],
    "GPU util. %": [float(r["gpu_util_pct"]) for r in sp],
    "Unified memory used %": [100 * (1 - int(r["mem_available_mib"]) / int(r["mem_total_mib"])) for r in sp],
    "Disk used %": [100 * (1 - int(r["disk_free_gb"]) / int(r["disk_total_gb"])) for r in sp],
}
fig, ax = plt.subplots(figsize=(6.4, 2.8))
w = 0.2
for i, (lab, vals) in enumerate(metrics.items()):
    xs = [j + (i - 1.5) * w for j in range(len(names))]
    b = ax.bar(xs, vals, w, label=lab, color=[GRAY, RED, ORANGE, BLUE][i])
    ax.bar_label(b, fmt="%.0f", fontsize=7, padding=1)
ax.set_xticks(range(len(names)), names)
ax.set_ylim(0, 110)
ax.set_ylabel("%")
ax.set_title("Research Sparks during the WP2 grid, 2026-11-26 04:11 UTC (no failed jobs)", fontsize=9)
ax.legend(ncol=4, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.12), frameon=False)
save(fig, "spark_status_2026-11-26T0411Z")

# 2. RunPod prepaid balance over the rental night
bal = rows("runpod_balance.csv")
t = [ts(r["time_utc"]) for r in bal]
v = [float(r["balance_usd"]) for r in bal]
fig, ax = plt.subplots(figsize=(6.4, 2.6))
ax.step(t, v, where="post", color=BLUE)
ax.plot(t, v, "o", ms=3, color=BLUE)
for r, x, y in zip(bal, t, v):
    if r["event"]:
        ax.annotate(r["event"], (x, y), xytext=(3, 6), textcoords="offset points", fontsize=6, color=GRAY)
ax.set_ylabel("Balance (US$)")
ax.set_ylim(0, max(v) * 1.25)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax.set_xlabel("UTC, 2026-11-25 to 26")
ax.set_title("RunPod prepaid balance during the WP2 rentals", fontsize=9)
save(fig, "runpod_balance_2026-11-26")

# 3. Download throughput: the Spark site link is the bottleneck
th = rows("pull_throughput.csv")
lab = [f"{r['path']}\n{r['time_utc'][11:16]} UTC" for r in th]
val = [float(r["mb_per_s"]) for r in th]
col = [BLUE if "laptop" in r["path"] else (ORANGE if "test" in r["path"] else GRAY) for r in th]
fig, ax = plt.subplots(figsize=(6.4, 3.6))
b = ax.barh(range(len(val)), val, color=col)
ax.bar_label(b, fmt="%.2f", fontsize=7, padding=2)
ax.set_yticks(range(len(val)), lab, fontsize=6)
ax.invert_yaxis()
ax.set_xlabel("MB/s")
ax.set_title("Download throughput from RunPod pods\n(gray: running pulls; orange: single tests at the Spark site; blue: another site)", fontsize=8)
save(fig, "pull_throughput_2026-11-26")

# 4. Rental timeline
pods = [r for r in rows("rented_pods.csv") if r["created_utc"]]
end = datetime(2026, 11, 26, 4, 12)
fig, ax = plt.subplots(figsize=(6.4, 2.2))
for i, r in enumerate(pods):
    s = ts(r["created_utc"])
    e = s.replace(minute=s.minute + 2) if "terminated" in r["state_2026-11-26T0412Z"] else end
    c = RED if "terminated" in r["state_2026-11-26T0412Z"] else BLUE
    ax.barh(i, mdates.date2num(e) - mdates.date2num(s), left=mdates.date2num(s), color=c, height=0.5)
    ax.text(mdates.date2num(e), i, f"  {r['cloud'].lower()} US${r['usd_per_hour']}/h; {r['state_2026-11-26T0412Z']}",
            va="center", fontsize=6)
ax.set_yticks(range(len(pods)), [f"{r['card']} ({r['pod_id'][:6]})" for r in pods], fontsize=7)
ax.invert_yaxis()
ax.xaxis_date()
ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax.set_xlim(mdates.date2num(datetime(2026, 11, 25, 17, 30)), mdates.date2num(datetime(2026, 11, 26, 8, 30)))
ax.set_xlabel("UTC (bars run to 04:12, the report time)")
ax.set_title("Rented pods for WP2 (red: terminated host with unusable CUDA)", fontsize=9)
save(fig, "rental_timeline_2026-11-26")
print("figures written to", F)
