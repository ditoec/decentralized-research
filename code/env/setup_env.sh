#!/usr/bin/env bash
# Build the research environment from the lock files, identically on arm64 (DGX Spark, inside
# the research container) and x86-64 (RunPod pod). Usage:
#
#   env/setup_env.sh [main|alt]        # default: main
#
# Environment:
#   ESJ_HOME   where venvs, ComfyUI and models live (default: $HOME/esj)
#
# main = Python 3.12.13, torch 2.14.1+cu130 (the study's stack, needs driver >= 580)
# alt  = Python 3.12.13, torch 2.13.0+cu129 (second software stack for the L-factor check)
# All other packages are pinned in env/lock-<stack>.txt; the locks were compiled for both
# aarch64 and x86_64 and are identical, so both architectures run the same versions.
set -euo pipefail
STACK="${1:-main}"
PYVER=3.12.13
HERE="$(cd "$(dirname "$0")/.." && pwd)"          # .../code
ESJ_HOME="${ESJ_HOME:-$HOME/esj}"
case "$STACK" in
  main) CU=cu130 ;;
  alt)  CU=cu129 ;;
  *) echo "unknown stack $STACK" >&2; exit 2 ;;
esac
mkdir -p "$ESJ_HOME"
export UV_CACHE_DIR="$ESJ_HOME/.uv-cache" UV_PYTHON_INSTALL_DIR="$ESJ_HOME/python" UV_HTTP_TIMEOUT=600 UV_HTTP_RETRIES=8
# always the pinned uv: images may ship an older one that lacks an x86_64 build of $PYVER
UV_VER=0.13.9
if [ "$("$ESJ_HOME/bin/uv" --version 2>/dev/null | cut -d' ' -f2)" != "$UV_VER" ]; then
  curl -LsSf "https://astral.sh/uv/$UV_VER/install.sh" | env UV_INSTALL_DIR="$ESJ_HOME/bin" INSTALLER_NO_MODIFY_PATH=1 sh
fi
export PATH="$ESJ_HOME/bin:$PATH"
VENV="$ESJ_HOME/venv-$STACK"
uv python install "$PYVER"
[ -x "$VENV/bin/python" ] || uv venv --python "$PYVER" "$VENV"
uv pip install --python "$VENV/bin/python" --index-strategy unsafe-best-match \
  --extra-index-url "https://download.pytorch.org/whl/$CU" -r "$HERE/env/lock-$STACK.txt"
uv pip install --python "$VENV/bin/python" --no-deps -e "$HERE"
TRAJVER_COMFYUI="${TRAJVER_COMFYUI:-$ESJ_HOME/ComfyUI}" bash "$HERE/tools/fetch_comfyui.sh"
"$VENV/bin/python" - <<'PY'
import platform, sys, torch
print("python", sys.version.split()[0], platform.machine())
print("torch", torch.__version__, "cuda", torch.version.cuda, "cudnn", torch.backends.cudnn.version())
if torch.cuda.is_available():
    print("gpu", torch.cuda.get_device_name(), torch.cuda.get_device_capability())
    x = torch.randn(256, 256, device="cuda"); print("matmul ok", float((x @ x).sum()) == float((x @ x).sum()))
PY
echo "venv: $VENV  (export TRAJVER_COMFYUI=${TRAJVER_COMFYUI:-$ESJ_HOME/ComfyUI})"
