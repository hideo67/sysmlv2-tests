#!/usr/bin/env bash
# Run test suites against the locally built MDKs.
#   ./run-all.sh                 run every suite
#   ./run-all.sh opensysml-go    run only the named suite(s)
#   ./run-all.sh --list          list suite names
# Results: results/<suite>.csv (one row per test case); raw output: results/logs/<suite>.log.
# results/ is git-ignored. A table of all results is written to results/report-all.md.
# Prerequisites: OpenSysML `make build-grpc`; Pilot Implementation `mvn -DskipTests package` (JDK 21).
cd "$(dirname "$0")" || exit 2
export RESULTS_DIR="$PWD/results"
JDK21=/usr/lib/jvm/java-21-openjdk-amd64
SUITES=(opensysml-py opensysml-go sysml-toolkit-rs pilot-java)

run_suite() {
  case "$1" in
    opensysml-py)     cd test-opensysml-py && .venv/bin/python -m pytest -q ;;
    opensysml-go)     cd test-opensysml-go && go test -v ./... ;;
    sysml-toolkit-rs) cd test-sysml-toolkit-rs && cargo test --release -- --nocapture ;;
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
for s in "${selected[@]}"; do
  echo "== $s"
  rm -f "results/$s.csv"
  ( run_suite "$s" ) > "results/logs/$s.log" 2>&1 || { rc=1; echo "   (test failures; see results/logs/$s.log)"; }
  [[ -f results/$s.csv ]] && echo "   $(python3 -c 'import csv,sys; print(sum(1 for _ in csv.DictReader(open(sys.argv[1]))))' "results/$s.csv") cases recorded" ||
    { echo "   NO RESULTS WRITTEN (build or setup problem; see log)"; rc=1; }
done

# Tabulate every CSV in results/ (including suites not run this time).
if ./report.py --details > results/report-all.md; then
  echo "== report: results/report-all.md"
else
  echo "== report: failed (see above)"; rc=1
fi
exit $rc
