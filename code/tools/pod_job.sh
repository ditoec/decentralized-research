#!/usr/bin/env bash
# Runs inside a RunPod pod (runbook §3.4 item 2). The operator has PUT code.tar.gz into /work.
#
#   bash /work/code/tools/pod_job.sh <workload.sh> [stack]
#
# Steps: build the locked environment (env/setup_env.sh), fetch the models named in
# experiments/configs/models.json and verify their sha256, record the node (nvidia-smi -q, GPU UUID,
# driver, data center), run the workload with TRAJVER_RUNS=/work/runs, then pack every run folder
# into /work/out/<run_id>.tar with a .sha256 for tools/pull_run.py. Writes /work/out/DONE or FAILED.
# Pod cost fields come from the environment the operator set at creation:
#   POD_HOURLY_USD, POD_CLOUD, RUNPOD_POD_ID (set by RunPod), RUNPOD_DC_ID (set by RunPod)
set -uo pipefail
WORKLOAD="$1"; STACK="${2:-main}"
export ESJ_HOME=/work/esj TRAJVER_RUNS=/work/runs TRAJVER_COMFYUI=/work/esj/ComfyUI
mkdir -p /work/out /work/runs /work/models/checkpoints /work/models/loras
exec > >(tee -a /work/out/pod_job.log) 2>&1
fail() { echo "FAILED: $*"; echo "$*" > /work/out/FAILED; exit 1; }
cd /work/code || fail "no code"
command -v git >/dev/null || (apt-get update -qq && apt-get install -y -qq git curl >/dev/null) || fail "apt"
env/setup_env.sh "$STACK" || fail "setup_env"
PY=/work/esj/venv-$STACK/bin/python
"$PY" - <<'PY' || fail "models"
import hashlib, json, os, subprocess, urllib.request
from pathlib import Path
cfg = json.loads(Path("../experiments/configs/models.json").read_text())
need = os.environ.get("POD_MODELS", "").split(",")
for m in cfg["models"]:
    if need != [""] and m["filename"] not in need:
        continue
    dst = Path("/work/models") / m["dir"] / m["filename"]
    if not dst.exists():
        subprocess.run(["curl", "-sSfL", "--retry", "5", "-C", "-", "-o", str(dst), m["url"]], check=True)
    h = hashlib.sha256()
    with open(dst, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    assert h.hexdigest() == m["sha256"], f"sha256 mismatch for {m['filename']}"
    print("model ok", m["filename"])
PY
nvidia-smi -q > /work/out/nvidia-smi-q.txt 2>&1
lscpu > /work/out/lscpu.txt 2>&1  # P1 depends on the host CPU and its PyTorch build
cat > /work/out/pod.json <<EOF
{"provider": "runpod", "pod_id": "${RUNPOD_POD_ID:-}", "data_center": "${RUNPOD_DC_ID:-}",
 "cloud_type": "${POD_CLOUD:-}", "hourly_rate_usd": ${POD_HOURLY_USD:-null},
 "gpu_uuid": "$(nvidia-smi --query-gpu=uuid --format=csv,noheader | head -1)",
 "driver": "$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)",
 "job_start_unix": $(date +%s)}
EOF
PATH="/work/esj/venv-$STACK/bin:$PATH" bash "$WORKLOAD" || fail "workload"
cd /work/runs && for r in */; do
  r="${r%/}"; cp /work/out/pod.json /work/out/nvidia-smi-q.txt /work/out/lscpu.txt "$r/logs/" 2>/dev/null
  tar -cf "/work/out/$r.tar" "$r" && sha256sum "/work/out/$r.tar" | cut -d' ' -f1 > "/work/out/$r.tar.sha256"
done
ls /work/out/*.tar | xargs -n1 basename > /work/out/INDEX
echo ok > /work/out/DONE
