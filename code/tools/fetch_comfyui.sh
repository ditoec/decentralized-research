#!/usr/bin/env bash
# Clone ComfyUI at the commit pinned for the study into code/.cache/ComfyUI (git-ignored).
set -euo pipefail
PINNED=8b25bbc371b73e876996cf14c917d075d78de2ee
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${TRAJVER_COMFYUI:-$HERE/.cache/ComfyUI}"
if [ ! -d "$DEST/.git" ]; then
  git clone --filter=blob:none https://github.com/Comfy-Org/ComfyUI.git "$DEST"
fi
git -C "$DEST" fetch --quiet origin "$PINNED" 2>/dev/null || true
git -C "$DEST" checkout --quiet "$PINNED"
echo "ComfyUI at $(git -C "$DEST" rev-parse HEAD) in $DEST"
