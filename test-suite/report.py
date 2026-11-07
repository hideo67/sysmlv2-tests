#!/usr/bin/env python3
"""Gather results/*.csv into a table: one row per test case ID, one column per suite.

  ./report.py            versions tested, per-matrix summary, and the full results table
                         (versions come from results/<suite>.version.json, written by run-all.sh)
  ./report.py --details  also list the detail text of every non-pass
  ./report.py --csv      emit the merged table as CSV instead
"""
import argparse
import csv
import fnmatch
import json
import sys
from collections import defaultdict
from pathlib import Path

SYMBOL = {"pass": "PASS", "fail": "FAIL", "unsupported": "UNSUP", "error": "ERROR", "skip": "SKIP"}

# Tracked files an MDK's own build rewrites (README, "Build the MDKs"): a difference in
# them is the build's output for the tested commit, not a change to its source.
BUILD_OUTPUTS = {
    "SysML v2 Pilot Implementation": {
        "org.omg.sysml.logic.bundle/lib/org.omg.sysml.logic-*.jar",
        "org.omg.sysml.model.bundle/lib/org.omg.sysml.model-*.jar",
    },
}


def print_versions(suites, versions):
    """The MDK versions each suite ran against (results/<suite>.version.json)."""
    print("# SysML v2 MDK test results")
    print()
    commits = {v.get("test_suite_commit", "") for v in versions.values()}
    if len(commits) == 1 and "" not in commits:
        dirty = any(v.get("test_suite_local_changes") for v in versions.values())
        print(f"Test suite commit: `{commits.pop()[:12]}`" + (" (with uncommitted changes)" if dirty else ""))
        print()
    print("## Versions tested")
    print()
    print("|suite|MDK|version (git describe)|commit|commit date|standard library|API exercised|toolchain|run at (UTC)|")
    print("|--|--|--|--|--|--|--|--|--|")
    notes = []
    for s in suites:
        v = versions.get(s)
        if not v:
            print(f"|{s}|not recorded|||||||")
            continue
        short = v["commit"][:10]
        commit = f"[`{short}`]({v['repo'].removesuffix('.git')}/commit/{v['commit']})" if "github.com" in v["repo"] else f"`{short}`"
        print(f"|{s}|{v['mdk']}|`{v['describe']}` ({v['branch']})|{commit}|{v['commit_date'][:10]}|"
              f"{v['library']}|{v['api']}|{v['toolchain']}|{v['run_at'].replace('T', ' ').rstrip('Z')}|")
        changed = v.get("local_changes") or []
        built = [p for p in changed if any(fnmatch.fnmatchcase(p, g) for g in BUILD_OUTPUTS.get(v["mdk"], ()))]
        edited = [p for p in changed if p not in built]
        if edited:
            notes.append(f"- {s}: the {v['mdk']} checkout differs from its commit in "
                         + ", ".join(f"`{p}`" for p in edited))
        if built:
            notes.append(f"- {s}: rewritten by the {v['mdk']} build of the tested commit, as expected "
                         "(the build regenerates these committed files; no source change): "
                         + ", ".join(f"`{p}`" for p in built))
    if notes:
        print()
        print("Local changes at run time (tracked files only):")
        print()
        print("\n".join(notes))
    print()


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
        # a suite keeps its column even when it recorded nothing (its cells then show "-")
        if f.stem not in suites:
            suites.append(f.stem)
        with open(f, newline="") as fh:
            for r in csv.DictReader(fh):
                if r["suite"] not in suites:
                    suites.append(r["suite"])
                ids.add(r["id"])
                cell[(r["id"], r["suite"])] = r["outcome"]
                detail[(r["id"], r["suite"])] = r["detail"]
    ids = sorted(ids)
    versions = {}
    for s in suites:
        vf = Path(a.dir) / f"{s}.version.json"
        if vf.exists():
            versions[s] = json.loads(vf.read_text())

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

    print_versions(suites, versions)

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
    for s in suites:
        recorded = sum(1 for i in ids if (i, s) in cell)
        if recorded < len(ids):
            print(f"**Warning:** {s} recorded {recorded} of {len(ids)} cases; the missing ones show as `-` "
                  f"(see results/logs/{s}.log).")
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
