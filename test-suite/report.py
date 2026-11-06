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

    def totals(subset, s):
        n = defaultdict(int)
        for i in subset:
            if (i, s) in cell:
                n[cell[(i, s)]] += 1
        return n

    # summary per matrix: pass/fail/unsupported/error for each suite
    matrices = sorted({i.split("-")[0] for i in ids})
    print("## Summary (pass / fail / unsupported / error)")
    print()
    print("|matrix|cases|" + "|".join(suites) + "|")
    print("|--|--:|" + "|".join(":-:" for _ in suites) + "|")
    for mx in matrices + ["all"]:
        subset = ids if mx == "all" else [i for i in ids if i.split("-")[0] == mx]
        cells = []
        for s in suites:
            n = totals(subset, s)
            cells.append(f"{n['pass']} / {n['fail']} / {n['unsupported']} / {n['error']}" if n else "-")
        print(f"|{'**all**' if mx == 'all' else mx}|{len(subset)}|" + "|".join(cells) + "|")
    print()

    print("## Results")
    print()
    show = lambda i, s: SYMBOL.get(cell.get((i, s)), "-") if (i, s) in cell else "-"
    print("|ID|" + "|".join(suites) + "|")
    print("|--|" + "|".join(":-:" for _ in suites) + "|")
    for i in ids:
        print(f"|{i}|" + "|".join(show(i, s) for s in suites) + "|")

    if a.details:
        print()
        print("## Details of results other than pass")
        print()
        for i in ids:
            for s in suites:
                if cell.get((i, s), "pass") != "pass":
                    print(f"- {i} [{s}] {cell[(i, s)]}: {detail[(i, s)]}")


main()
