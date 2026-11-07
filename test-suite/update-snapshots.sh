#!/usr/bin/env bash
# Update the committed SNAPSHOT reports from results/:
#   report-all-SNAPSHOT.md   ./report.py --details   (every suite of run-all.sh)
#   census-SNAPSHOT.md       ./census_report.py      (every census of run-census.sh)
#
#   ./update-snapshots.sh                  both, from the results already in results/
#   ./update-snapshots.sh report           only the test result snapshot
#   ./update-snapshots.sh census           only the census snapshot
#   ./update-snapshots.sh --run [...]      run the suites / censuses first (all of them)
#   ./update-snapshots.sh --force [...]    write even if the checks below fail
#
# A snapshot tabulates whatever results/ holds, so before writing it this checks that:
#   - every suite (census) has results, and every suite recorded every test case;
#   - the suites of one MDK all ran against the same commit (no mix of old and new runs).
# It warns, but goes on, if the results were not produced at the test suite's HEAD
# with a clean tree (the report states the commit it ran at either way).
# It does not commit: review `git diff` and commit the snapshots yourself.
# Build the MDKs first (build-*.sh); see "Building and running" in ../README.md.
set -uo pipefail
cd "$(dirname "$0")" || exit 2

run=0 force=0 which=()
for a in "$@"; do
  case "$a" in
    --run) run=1 ;;
    --force) force=1 ;;
    report|census) which+=("$a") ;;
    *) echo "unknown argument '$a' (report, census, --run, --force)" >&2; exit 2 ;;
  esac
done
[[ ${#which[@]} -eq 0 ]] && which=(report census)

check() {  # check <report|census>: completeness and one commit per MDK
  python3 -I - "$1" "$(./run-all.sh --list | tr '\n' ' ')" "$(./run-census.sh --list | tr '\n' ' ')" <<'EOF'
import csv, glob, json, subprocess, sys
from pathlib import Path
kind, suites, censuses = sys.argv[1], sys.argv[2].split(), sys.argv[3].split()
res = Path("results")
problems, warnings, commits = [], [], {}
total = sum(len(json.load(open(f))["cases"]) for f in glob.glob("data/cases/*.json"))
names = suites if kind == "report" else censuses
for s in names:
    data = res / (f"{s}.csv" if kind == "report" else f"census-{s}.json")
    ver = res / (f"{s}.version.json" if kind == "report" else f"census-{s}.version.json")
    if not data.exists() or not ver.exists():
        problems.append(f"{s}: no results ({data} / {ver})"); continue
    if kind == "report":
        n = sum(1 for _ in csv.DictReader(open(data)))
        if n != total:
            problems.append(f"{s}: {n} of {total} cases recorded")
    v = json.load(open(ver))
    commits.setdefault(v["mdk"], {}).setdefault(v["commit"][:10], []).append(s)
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if v.get("test_suite_commit") != head or v.get("test_suite_local_changes"):
        warnings.append(f"{s}: ran at test suite {v.get('test_suite_commit', '?')[:12]}"
                        f"{' with local changes' if v.get('test_suite_local_changes') else ''},"
                        f" HEAD is {head[:12]}")
for mdk, by in commits.items():
    if len(by) > 1:
        problems.append(f"{mdk}: suites ran against different commits: "
                        + "; ".join(f"{c} ({', '.join(ss)})" for c, ss in by.items()))
for w in warnings: print(f"   warning: {w}")
for p in problems: print(f"   {p}")
sys.exit(1 if problems else 0)
EOF
}

rc=0
for k in "${which[@]}"; do
  if [[ $k == report ]]; then
    runner=./run-all.sh gen=(./report.py --details) out=report-all-SNAPSHOT.md
  else
    runner=./run-census.sh gen=(./census_report.py) out=census-SNAPSHOT.md
  fi
  if (( run )); then
    echo "== $k: $runner"
    $runner  # non-zero is normal while the MDKs have defects; the checks decide
  fi
  echo "== $k: checking results/"
  if ! check "$k"; then
    if (( force )); then echo "   (--force: writing anyway)"
    else echo "   not written: $out (rerun the suites named above, or pass --force)"; rc=1; continue; fi
  fi
  tmp=$(mktemp)
  if "${gen[@]}" > "$tmp"; then
    mv "$tmp" "$out"; echo "== $k: wrote $out"
  else
    rm -f "$tmp"; echo "== $k: ${gen[*]} failed; $out left as it was"; rc=1
  fi
done
git diff --stat -- report-all-SNAPSHOT.md census-SNAPSHOT.md
exit $rc
