#!/usr/bin/env bash
# Build, from the local sysml-toolkit checkout, only what the sysml-toolkit-rs
# suites (and the census) use: the sysmlv2-parser crate, with the standard library
# from the spec-refs/SysML-v2-Release submodule.
# The suite compiles the crate as a (dev-)path dependency, so it is built here into
# the suite's own target directory and profile, which `cargo test --release` then
# reuses: `--no-run` compiles the crate and the suite's test binaries, runs nothing.
# (`cargo build -p sysmlv2-parser` would be narrower, but cargo panics on -p naming a
# dev-only dependency.) No other crate of the workspace (CLI, LSP, wasm, Python
# bindings, ...) is built.
#   ./build-sysml-toolkit.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MDK="$HERE/../sysml-toolkit"

[[ -d "$MDK" ]] || { echo "no sysml-toolkit checkout at $MDK (see ../README.md, step 1)" >&2; exit 2; }

echo "== sysml-toolkit: standard library submodule (spec-refs/SysML-v2-Release)"
git -C "$MDK" submodule update --init --filter=blob:none spec-refs/SysML-v2-Release

echo "== sysml-toolkit: sysmlv2-parser (into test-sysml-toolkit-rs/target)"
cargo test --release --no-run --manifest-path "$HERE/test-sysml-toolkit-rs/Cargo.toml"

echo "== sysml-toolkit: done"
