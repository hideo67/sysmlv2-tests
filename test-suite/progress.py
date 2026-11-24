#!/usr/bin/env python3
"""Write PROGRESS-SNAPSHOT.md: how the results moved, snapshot by snapshot.

  ./progress.py            write PROGRESS-SNAPSHOT.md
  ./progress.py --stdout   print it instead

The data is the history of report-all-SNAPSHOT.md in git: every committed version of it
is one point, read from its "Versions tested" and "Summary" tables. If the working tree's
report-all-SNAPSHOT.md differs from HEAD's (update-snapshots.sh has just written it), it is
the last point. Release tags mark the last snapshot each tag contains.

Counted per suite: fail + error, the cases an MDK answered wrongly or could not answer
for an error. Unsupported cases (a read the API does not offer) are left out of the
charts; the table lists them per snapshot only in the case count.
update-snapshots.sh runs this after writing the snapshots. It never commits.
"""
import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNAPSHOT = "test-suite/report-all-SNAPSHOT.md"
OUT = HERE / "PROGRESS-SNAPSHOT.md"
REPO = "https://github.com/hideo67/sysmlv2-tests"

# Table columns, in order: suite name, short heading.
SUITES = [
    ("opensysml-py-props", "py-props"), ("opensysml-go-props", "go-props"),
    ("opensysml-py", "py"), ("opensysml-go", "go"), ("opensysml-rs", "rs"),
    ("opensysml-ts", "ts"), ("opensysml-ts-wasm", "ts-wasm"), ("opensysml-java", "java"),
    ("sysml-toolkit-rs", "toolkit"), ("sysml-toolkit-rs-checked", "toolkit-checked"),
    ("pilot-java", "Pilot"),
]
# One chart per MDK and API: title, suite (the first suite present in the snapshot).
CHARTS = [
    ("OpenSysML, GetElementProperties (opensysml-py-props)", ["opensysml-py-props", "opensysml-go-props"]),
    ("OpenSysML, Symbol API (opensysml-py)", ["opensysml-py"]),
    ("sysml-toolkit, derived() (sysml-toolkit-rs)", ["sysml-toolkit-rs"]),
    ("sysml-toolkit, checked property() (sysml-toolkit-rs-checked)", ["sysml-toolkit-rs-checked"]),
]
MDKS = [("OpenSysML", "OpenSysML"), ("sysml-toolkit", "sysml-toolkit"), ("SysML v2 Pilot Implementation", "Pilot")]


def git(*args):
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True, check=True).stdout


def table(text, header_start):
    """The rows (lists of cells) of the first markdown table whose header starts with `header_start`."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(header_start):
            head = [c.strip() for c in line.strip("|").split("|")]
            rows = []
            for row in lines[i + 2:]:
                if not row.startswith("|"):
                    break
                rows.append([c.strip() for c in row.strip("|").split("|")])
            return head, rows
    return None, []


def parse(text):
    """Suite commit, MDK versions, case count and per-suite totals of one snapshot."""
    m = re.search(r"Test suite commit: `([0-9a-f]+)`", text)
    point = {"suite_commit": m[1] if m else "?", "mdk": {}, "totals": {}, "cases": 0}
    head, rows = table(text, "|suite|MDK|")
    if head:
        col = {h: i for i, h in enumerate(head)}
        for r in rows:
            mdk = r[col["MDK"]]
            if mdk in point["mdk"]:
                continue
            commit = re.search(r"`([0-9a-f]+)`", r[col["commit"]])
            describe = re.search(r"`([^`]+)`", r[col["version (git describe)"]])
            point["mdk"][mdk] = {"commit": commit[1] if commit else "?", "describe": describe[1] if describe else "?"}
    head, rows = table(text, "|matrix|cases|")
    if head:
        suites = head[2:]
        for r in rows:
            if r[0].strip("*") == "all":
                continue
            point["cases"] += int(r[1])
            for s, cell in zip(suites, r[2:]):
                nums = [int(x) for x in re.findall(r"\d+", cell)]
                if len(nums) == 4:
                    t = point["totals"].setdefault(s, [0, 0, 0, 0])
                    point["totals"][s] = [a + b for a, b in zip(t, nums)]
    return point


def history():
    """One point per committed version of the snapshot, oldest first, and the working tree's."""
    points = []
    log = git("log", "--reverse", "--format=%H%x09%ad%x09%s", "--date=short", "--", f":(top){SNAPSHOT}")
    for line in log.splitlines():
        sha, day, subject = line.split("\t", 2)
        point = parse(git("show", f"{sha}:{SNAPSHOT}"))
        point.update(sha=sha, date=day, subject=subject, tags=[])
        points.append(point)
    tags = {}
    for tag in git("tag", "--list", "v*").split():
        sha = git("log", "-1", "--format=%H", tag, "--", f":(top){SNAPSHOT}").strip()
        tags.setdefault(sha, []).append(tag)
    for p in points:
        p["tags"] = sorted(tags.get(p["sha"], []))
    work = (HERE / "report-all-SNAPSHOT.md").read_text()
    if points and work != git("show", f"HEAD:{SNAPSHOT}"):
        point = parse(work)
        point.update(sha=None, date=date.today().isoformat(), tags=[],
                     subject="this snapshot (written with it, not yet committed)")
        points.append(point)
    return points


def bad(point, suite):
    t = point["totals"].get(suite)
    return None if t is None else t[1] + t[3]


def subject(p):
    s = re.sub(r"^(Snapshots updated|Test result snapshot updated|Test result snapshot added)[:.]?\s*", "", p["subject"])
    return (s or p["subject"]).replace("|", "\\|")


def label(p, points):
    """A short, unique x-axis label: the release tag, else month-day with a letter if repeated."""
    if p["tags"]:
        return p["tags"][-1]
    same = [q for q in points if q["date"] == p["date"] and not q["tags"]]
    md = p["date"][5:]
    return md if len(same) == 1 else f"{md}{'abcdefghijklmnopqrstuvwxyz'[same.index(p) % 26]}"


def chart_points(points):
    """The points a chart plots: the last snapshot of each day, and every tagged one (Mermaid
    labels every category, so one per snapshot crowds the axis; the table lists them all)."""
    keep = []
    for i, p in enumerate(points):
        last_of_day = i + 1 == len(points) or points[i + 1]["date"] != p["date"]
        if last_of_day or p["tags"]:
            keep.append(p)
    return keep


def chart(title, suites, points):
    xs, ys = [], []
    shown = chart_points(points)
    for p in shown:
        suite = next((s for s in suites if s in p["totals"]), None)
        if suite is None:
            continue
        xs.append(label(p, shown))
        ys.append(bad(p, suite))
    if not ys:
        return []
    top = max(ys) or 1
    return ["```mermaid", "xychart-beta", f'    title "{title}"',
            "    x-axis [" + ", ".join(f'"{x}"' for x in xs) + "]",
            f'    y-axis "fail + error" 0 --> {top + max(1, top // 10)}',
            "    line [" + ", ".join(str(y) for y in ys) + "]", "```", ""]


def render(points):
    last = points[-1]
    out = ["# Progress of the SysML v2 MDKs", "",
           "How the results moved, snapshot by snapshot. Each point is one version of",
           "[report-all-SNAPSHOT.md](report-all-SNAPSHOT.md), from its history in git.",
           "Generated by `test-suite/progress.py`, which `update-snapshots.sh` runs; do not edit by hand.", "",
           "The charts plot the last snapshot of each day and each release; the table lists every",
           "snapshot. They count **fail + error** per suite: cases an MDK answered wrongly, or could not",
           "answer for an error. Unsupported cases (a read the API does not offer) are left out.",
           "The suite grows over time: a release adds cases, and new cases may fail at first.",
           "So the count can rise without any MDK changing. Release tags mark the last snapshot",
           "each release contains; [DISCUSSIONS.md](../DISCUSSIONS.md) explains every step.", "",
           f"Latest: {last['cases']} cases, " + ", ".join(
               f"{name} `{last['mdk'][mdk]['describe'] if name == 'sysml-toolkit' else last['mdk'][mdk]['commit']}`"
               for mdk, name in MDKS if mdk in last["mdk"]) + ".", ""]
    out += ["## Charts", ""]
    for title, suites in CHARTS:
        out += chart(title, suites, points)
    out += ["The Pilot is the reference: its expected values are the suite's, and it has failed no",
            "case since the first snapshot.", "",
            "## Snapshots", "",
            "Newest first. The suite columns give fail + error; – means the suite did not exist yet.", "",
            "|date|snapshot|release|cases|OpenSysML|sysml-toolkit|Pilot|"
            + "|".join(h for _, h in SUITES) + "|what changed|",
            "|--|--|--|--:|--|--|--|" + "|".join("--:" for _ in SUITES) + "|--|"]
    for p in reversed(points):
        snap = f"[`{p['sha'][:7]}`]({REPO}/commit/{p['sha']})" if p["sha"] else "working tree"
        rel = " ".join(f"[{t}]({REPO}/releases/tag/{t})" for t in p["tags"])
        mdk = []
        for name, short in MDKS:
            v = p["mdk"].get(name)
            mdk.append("–" if v is None else f"`{v['describe']}`" if short == "sysml-toolkit" else f"`{v['commit']}`")
        cells = ["–" if bad(p, s) is None else str(bad(p, s)) for s, _ in SUITES]
        out.append(f"|{p['date']}|{snap}|{rel}|{p['cases']}|" + "|".join(mdk) + "|" + "|".join(cells)
                   + f"|{subject(p)}|")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stdout", action="store_true", help="print instead of writing PROGRESS-SNAPSHOT.md")
    args = ap.parse_args()
    points = history()
    if not points:
        sys.exit("no committed report-all-SNAPSHOT.md in the git history")
    text = render(points)
    if args.stdout:
        sys.stdout.write(text)
    else:
        OUT.write_text(text)
        print(f"wrote {OUT.name}: {len(points)} snapshots")


if __name__ == "__main__":
    main()
