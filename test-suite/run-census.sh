#!/usr/bin/env bash
# Run the derived-property census against the locally built MDKs.
#   ./run-census.sh                       every census
#   ./run-census.sh sysml-toolkit-rs      only the named one(s)
#   ./run-census.sh --list                list census names
# The property list and corpora: data/census/derived-properties.json (data/gen_census.py).
# Results: results/census-<suite>.json and .version.json; raw output: results/logs/census-<suite>.log;
# the report: results/census-report.md. results/ is git-ignored.
# Prerequisites: those of run-all.sh (see "Building and running" in ../README.md).
cd "$(dirname "$0")" || exit 2
export RESULTS_DIR="$PWD/results"
export JDK21="${JDK21:-/usr/lib/jvm/java-21-openjdk-amd64}"
export CENSUS=1
CENSUSES=(pilot-java sysml-toolkit-rs opensysml-go-props)

run_census() {
  case "$1" in
    pilot-java)         cd test-sysml-v2-pilot-implementation-java &&
                        JAVA_HOME=$JDK21 PATH=$JDK21/bin:$PATH mvn -B test -Dtest=CensusTest ;;
    sysml-toolkit-rs)   cd test-sysml-toolkit-rs && cargo test --release --test census -- --nocapture ;;
    opensysml-go-props) cd test-opensysml-go && go test -count=1 -run TestCensus -v -timeout 60m ./... ;;
  esac
}

if [[ "$1" == "--list" ]]; then printf '%s\n' "${CENSUSES[@]}"; exit 0; fi
selected=("$@"); [[ ${#selected[@]} -eq 0 ]] && selected=("${CENSUSES[@]}")
for s in "${selected[@]}"; do
  [[ " ${CENSUSES[*]} " == *" $s "* ]] || { echo "unknown census '$s' (try --list)" >&2; exit 2; }
done

mkdir -p results/logs
rc=0
for s in "${selected[@]}"; do
  echo "== census $s"
  rm -f "results/census-$s.json" "results/census-$s.version.json"
  ( run_census "$s" ) > "results/logs/census-$s.log" 2>&1 || { rc=1; echo "   (failed; see results/logs/census-$s.log)"; }
  ./mdk_version.py "$s" > "results/census-$s.version.json" || echo "   (could not record the MDK version)"
  if [[ -f results/census-$s.json ]]; then
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1]))
for c,v in d["corpora"].items(): print("   %s: %d elements" % (c, v["elements"]))' "results/census-$s.json"
  else
    echo "   NO RESULTS RECORDED (see results/logs/census-$s.log)"; rc=1
  fi
done

if ./census_report.py > results/census-report.md; then
  echo "== report: results/census-report.md"
else
  echo "== report: failed (see above)"; rc=1
fi
exit $rc
