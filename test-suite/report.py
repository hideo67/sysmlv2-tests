#!/usr/bin/env python3
"""Gather results/*.csv into a table: one row per test case ID, one column per suite.

  ./report.py            markdown table plus per-suite totals
  ./report.py --details  also list the detail text of every non-pass
  ./report.py --csv      emit the merged table as CSV instead
"""
import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

SYMBOL = {"pass": "PASS", "fail": "FAIL", "unsupported": "UNSUP", "error": "ERROR", "skip": "SKIP"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=Path(__file__).resolve().parent / "results")
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--csv", action="store_true")
    a = ap.parse_args()

    files = sorted(Path(a.dir).glob("*.csv"))
    if not files:
        sys.exit(f"no CSV files in {a.dir}; run ./run-all.sh first")
    cell = {}                # (id, suite) -> outcome
    detail = {}              # (id, suite) -> text
    suites, ids = [], set()
    for f in files:
        with open(f, newline="") as fh:
            for r in csv.DictReader(fh):
                if r["suite"] not in suites:
                    suites.append(r["suite"])
                ids.add(r["id"])
                cell[(r["id"], r["suite"])] = r["outcome"]
                detail[(r["id"], r["suite"])] = r["detail"]
    ids = sorted(ids)

    if a.csv:
        w = csv.writer(sys.stdout)
        w.writerow(["id"] + suites)
        for i in ids:
            w.writerow([i] + [cell.get((i, s), "") for s in suites])
        return

    show = lambda i, s: SYMBOL.get(cell.get((i, s)), "-") if (i, s) in cell else "-"
    print("|ID|" + "|".join(suites) + "|")
    print("|--|" + "|".join(":-:" for _ in suites) + "|")
    for i in ids:
        print(f"|{i}|" + "|".join(show(i, s) for s in suites) + "|")
    print()
    print("|suite|pass|fail|unsupported|error|other|")
    print("|--|--:|--:|--:|--:|--:|")
    for s in suites:
        n = defaultdict(int)
        for i in ids:
            if (i, s) in cell:
                n[cell[(i, s)]] += 1
        other = sum(v for k, v in n.items() if k not in ("pass", "fail", "unsupported", "error"))
        print(f"|{s}|{n['pass']}|{n['fail']}|{n['unsupported']}|{n['error']}|{other}|")

    if a.details:
        print()
        for i in ids:
            for s in suites:
                if cell.get((i, s), "pass") != "pass":
                    print(f"- {i} [{s}] {cell[(i, s)]}: {detail[(i, s)]}")


main()
