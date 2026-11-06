#!/usr/bin/env bash
# Run test suites against the locally built MDKs.
#   ./run-all.sh                 run every suite
#   ./run-all.sh opensysml-go    run only the named suite(s)
#   ./run-all.sh --list          list suite names
# Results: results/<suite>.csv (one row per test case); raw output: results/logs/<suite>.log.
# results/ is git-ignored. A table of all results is written to results/report-all.md.
# Prerequisites: see "Building and running" in ../README.md.
# Set JDK21 to a JDK 21 home if it is not at the default path below.
cd "$(dirname "$0")" || exit 2
export RESULTS_DIR="$PWD/results"
export JDK21="${JDK21:-/usr/lib/jvm/java-21-openjdk-amd64}"
if [[ ! -x "$JDK21/bin/java" ]]; then
  echo "warning: no JDK at JDK21=$JDK21; the pilot-java suite needs JDK 21" >&2
fi
SUITES=(opensysml-py opensysml-go sysml-toolkit-rs sysml-toolkit-rs-checked pilot-java)

run_suite() {
  case "$1" in
    opensysml-py)     cd test-opensysml-py && .venv/bin/python -m pytest -q ;;
    opensysml-go)     cd test-opensysml-go && go test -v ./... ;;
    sysml-toolkit-rs) cd test-sysml-toolkit-rs &&
                      SYSML_TOOLKIT_READER=compatibility cargo test --release -- --nocapture ;;
    sysml-toolkit-rs-checked)
                      cd test-sysml-toolkit-rs &&
                      SYSML_TOOLKIT_READER=checked cargo test --release -- --nocapture ;;
    pilot-java)       cd test-sysml-v2-pilot-implementation-java &&
                      JAVA_HOME=$JDK21 PATH=$JDK21/bin:$PATH mvn -B test ;;
  esac
}

if [[ "$1" == "--list" ]]; then printf '%s\n' "${SUITES[@]}"; exit 0; fi
selected=("$@"); [[ ${#selected[@]} -eq 0 ]] && selected=("${SUITES[@]}")
for s in "${selected[@]}"; do
  [[ " ${SUITES[*]} " == *" $s "* ]] || { echo "unknown suite '$s' (try --list)" >&2; exit 2; }
done

mkdir -p results/logs
rc=0
total=$(python3 -c 'import json,glob; print(sum(len(json.load(open(f))["cases"]) for f in glob.glob("data/cases/*.json")))')
for s in "${selected[@]}"; do
  echo "== $s"
  rm -f "results/$s.csv" "results/$s.version.json"
  ( run_suite "$s" ) > "results/logs/$s.log" 2>&1 || { rc=1; echo "   (test failures; see results/logs/$s.log)"; }
  # record the MDK version this run exercised, next to its results
  ./mdk_version.py "$s" > "results/$s.version.json" || echo "   (could not record the MDK version)"
  # every case of every matrix must be recorded; fewer means a build, setup or model-loading problem
  n=0; [[ -f results/$s.csv ]] && n=$(python3 -c 'import csv,sys; print(sum(1 for _ in csv.DictReader(open(sys.argv[1]))))' "results/$s.csv")
  if (( n == 0 )); then
    echo "   NO RESULTS RECORDED (build, setup or model-loading problem; see results/logs/$s.log)"; rc=1
  elif (( n < total )); then
    echo "   ONLY $n OF $total CASES RECORDED (see results/logs/$s.log)"; rc=1
  else
    echo "   $n cases recorded"
  fi
done

# Tabulate every CSV in results/ (including suites not run this time).
if ./report.py --details > results/report-all.md; then
  echo "== report: results/report-all.md"
else
  echo "== report: failed (see above)"; rc=1
fi
exit $rc
