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
# Retention (runbook §3.5), also set at creation:
#   POD_RETENTION         per-run classes, e.g. 'wp2-*-test-*=O,*=F' (default '*=F': keep everything)
#   POD_DRAW_SEED_SHA256  sha256 of the operator's draw seed (trajver.retention newseed); required if
#                         any run is class O. The seed itself is NOT here: after the workload the pod
#                         writes out/GENERATED and waits for the operator to PUT secret/draw_seed.hex
#                         (tools/pull_run.py --reveal-seed does this), then extracts and discards.
set -uo pipefail
WORKLOAD="$1"; STACK="${2:-main}"
export ESJ_HOME=/work/esj TRAJVER_RUNS=/work/runs TRAJVER_COMFYUI=/work/esj/ComfyUI
POD_RETENTION="${POD_RETENTION:-*=F}"
export TRAJVER_DRAW_SEED_SHA256="${POD_DRAW_SEED_SHA256:-}"
rm -f /work/secret/draw_seed.hex  # a seed may only arrive after generation
mkdir -p /work/out /work/runs /work/models/checkpoints /work/models/loras
exec > >(tee -a /work/out/pod_job.log) 2>&1
fail() { echo "FAILED: $*"; echo "$*" > /work/out/FAILED; exit 1; }
cd /work/code || fail "no code"
command -v git >/dev/null || (apt-get update -qq && apt-get install -y -qq git curl >/dev/null) || fail "apt"
env/setup_env.sh "$STACK" || fail "setup_env"
PY=/work/esj/venv-$STACK/bin/python
# some RunPod hosts expose the card to nvidia-smi but not to CUDA ("CUDA unknown error", seen
# 2026-11-25 on an RTX 4090 host); without this check the workload would run on the CPU
"$PY" -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null \
  || fail "CUDA not usable on this host: terminate the pod and rent another"
# no image on a pod: the environment is pinned by its lock file, recorded in the same manifest field
export TRAJVER_IMAGE_DIGEST="lock-$STACK:sha256:$(sha256sum "env/lock-$STACK.txt" | cut -d' ' -f1)"
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
 "draw_seed_sha256": "${TRAJVER_DRAW_SEED_SHA256}", "retention": "${POD_RETENTION}",
 "job_start_unix": $(date +%s)}
EOF
PATH="/work/esj/venv-$STACK/bin:$PATH" bash "$WORKLOAD" || fail "workload"
# retention: extract the class-O/I bundles and discard full trajectories before anything is packed
cd /work/code
CLASSES=$("$PY" -c "import sys,pathlib; from trajver.retention import class_for; print(' '.join(class_for(p.name, sys.argv[1]) for p in sorted(pathlib.Path('/work/runs').iterdir()) if p.is_dir()))" "$POD_RETENTION") || fail "retention map"
SEEDARG=()
if [[ " $CLASSES " == *" O "* ]]; then
  [ -n "$TRAJVER_DRAW_SEED_SHA256" ] || fail "class O runs need POD_DRAW_SEED_SHA256 set at pod creation"
  echo generated > /work/out/GENERATED
  echo "waiting for the draw seed (PUT secret/draw_seed.hex)"
  for _ in $(seq 1 8640); do [ -s /work/secret/draw_seed.hex ] && break; sleep 10; done
  [ -s /work/secret/draw_seed.hex ] || fail "no draw seed within 24 h"
  SEEDARG=(--seed-file /work/secret/draw_seed.hex)
fi
"$PY" -m trajver.retention extract /work/runs/*/ --map "$POD_RETENTION" "${SEEDARG[@]}" || fail "retention extract"
"$PY" -m trajver.retention check /work/runs/*/ || fail "retention check"
cd /work/runs && for r in */; do
  r="${r%/}"; cp /work/out/pod.json /work/out/nvidia-smi-q.txt /work/out/lscpu.txt "$r/logs/" 2>/dev/null
  tar -cf "/work/out/$r.tar" "$r" && sha256sum "/work/out/$r.tar" | cut -d' ' -f1 > "/work/out/$r.tar.sha256"
done
ls /work/out/*.tar | xargs -n1 basename > /work/out/INDEX
echo ok > /work/out/DONE
rm -f /work/out/GENERATED
