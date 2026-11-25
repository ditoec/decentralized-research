#!/usr/bin/env bash
# Starts a fresh solana-test-validator with the built program preloaded at its declared id.
# Run from code/program after scripts/build.sh. Ledger under .anchor/ (git-ignored).
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/share/solana/install/active_release/bin:$PATH"
ID=$(node -e 'console.log(require("./idl/trajescrow.json").address)')
exec solana-test-validator --reset --quiet --ledger .anchor/replay-ledger \
  --bpf-program "$ID" target/deploy/trajescrow.so "$@"
