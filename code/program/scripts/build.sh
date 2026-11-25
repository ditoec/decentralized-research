#!/usr/bin/env bash
# Builds the program and its IDL with the workaround for Anchor 1.2.2 + platform-tools v1.57
# (runbook section 7, status note). Run from code/program.
#   1. `anchor build --no-idl -- --no-rustup-override` with platform-tools' rustc first on PATH,
#      because the workspace rust-toolchain.toml (1.89) would otherwise override the SBF toolchain;
#   2. `anchor idl build` with the host toolchain;
#   3. copy the IDL and TS types to idl/ (committed, used by the client, relay and replay).
set -euo pipefail
cd "$(dirname "$0")/.."
PT="${PLATFORM_TOOLS:-$HOME/.cache/solana/v1.57/platform-tools}"
SOLBIN="$HOME/.local/share/solana/install/active_release/bin"
export PATH="$SOLBIN:$HOME/.avm/bin:$PATH"
PATH="$PT/rust/bin:$PATH" anchor build --no-idl -- --no-rustup-override
anchor idl build -o target/idl/trajescrow.json -t target/types/trajescrow.ts
cp target/idl/trajescrow.json target/types/trajescrow.ts idl/
shasum -a 256 target/deploy/trajescrow.so
