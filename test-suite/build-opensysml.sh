#!/usr/bin/env bash
# Build, from the local OpenSysML checkout, only what the test suites use:
#   bin/sysml-grpc                            opensysml-py(-props), -rs, -ts, -java
#   internal/workspace/libs stdlib snapshot   compiling opensysml-go(-props)
#   bin/wasm/release/sysml-wasm.wasm
#     and wasm_exec.js                        opensysml-ts-wasm
#   client/node/dist                          opensysml-ts, opensysml-ts-wasm
#   client/java, installed into ~/.m2         opensysml-java
#   client/rust/opensysml, compiled into
#     test-opensysml-rs/target                opensysml-rs (warms the suite's build)
# The Python client needs no build: the suite's setup installs it in editable mode
# (see "Building and running" in ../README.md).
#   ./build-opensysml.sh            everything above
#   ./build-opensysml.sh grpc wasm  only the named parts: grpc wasm node java rust
# Set JDK21 to a JDK 21 home if it is not at the default path below.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MDK="$HERE/../OpenSysML"
JDK21="${JDK21:-/usr/lib/jvm/java-21-openjdk-amd64}"
PARTS=(grpc wasm node java rust)

[[ -d "$MDK" ]] || { echo "no OpenSysML checkout at $MDK (see ../README.md, step 1)" >&2; exit 2; }
selected=("$@"); [[ ${#selected[@]} -eq 0 ]] && selected=("${PARTS[@]}")
for p in "${selected[@]}"; do
  [[ " ${PARTS[*]} " == *" $p "* ]] || { echo "unknown part '$p' (one of: ${PARTS[*]})" >&2; exit 2; }
done
want() { [[ " ${selected[*]} " == *" $1 "* ]]; }

# grpc and wasm go through the Makefile so the binaries carry its version stamps
# (LDFLAGS). build-release-wasm also builds sysml-prod.wasm.gz, which no suite uses,
# so the wasm part is a target defined here from the Makefile's own variables.
# Both depend on stdlib-snapshot; one make invocation runs it once.
targets=()
want grpc && targets+=(build-grpc)
want wasm && targets+=(suite-wasm)
if [[ ${#targets[@]} -gt 0 ]]; then
  echo "== OpenSysML: make ${targets[*]}"
  make -C "$MDK" \
    --eval='suite-wasm: stdlib-snapshot
	@mkdir -p $(WASM_DIR)/release
	GOOS=js GOARCH=wasm $(GO_BUILD) -trimpath -o $(WASM_DIR)/release/sysml-wasm.wasm ./cmd/sysml-wasm
	@cp "$(shell go env GOROOT)/lib/wasm/wasm_exec.js" $(WASM_DIR)/release/wasm_exec.js
	@echo "✓ Built $(WASM_DIR)/release/sysml-wasm.wasm and wasm_exec.js ($(VERSION))"' \
    "${targets[@]}"
fi

if want node; then
  echo "== OpenSysML: TypeScript client (client/node/dist)"
  (cd "$MDK/client/node" && npm ci && npm run build)
fi

if want java; then
  echo "== OpenSysML: Java client (client/java, mvn install)"
  [[ -x "$JDK21/bin/java" ]] || { echo "no JDK at JDK21=$JDK21" >&2; exit 2; }
  JAVA_HOME="$JDK21" PATH="$JDK21/bin:$PATH" mvn -B -DskipTests -f "$MDK/client/java/pom.xml" install
fi

if want rust; then
  echo "== OpenSysML: Rust client (into test-opensysml-rs/target)"
  # the suite compiles the client as a (dev-)path dependency; building it here, in the
  # suite's own target directory and profile, is what `cargo test --release` reuses.
  # --no-run compiles the client and the suite's test binary and runs nothing
  # (cargo panics on `build -p` naming a dev-only dependency).
  cargo test --release --no-run --manifest-path "$HERE/test-opensysml-rs/Cargo.toml"
fi

echo "== OpenSysML: done"
