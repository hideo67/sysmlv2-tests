"""Writes one CSV row per test case to $RESULTS_DIR/opensysml-py.csv."""
import csv
import os
from pathlib import Path

SUITE = "opensysml-py"
_rows = []


def pytest_runtest_logreport(report):
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        pass
    else:
        return
    callspec = report.nodeid.split("[")[-1].rstrip("]")
    matrix = callspec.split("-")[0]
    if report.outcome == "passed":
        outcome, detail = "pass", ""
    elif report.outcome == "skipped":
        reason = str(report.longrepr[2]) if isinstance(report.longrepr, tuple) else str(report.longrepr)
        reason = reason.removeprefix("Skipped: ")
        if reason.startswith("UNSUPPORTED"):
            outcome, detail = "unsupported", reason.removeprefix("UNSUPPORTED: ")
        else:
            outcome, detail = "skip", reason
    else:
        outcome = "fail" if report.when == "call" and "AssertionError" in str(report.longrepr) else "error"
        errs = [l[1:].strip().removeprefix("test_matrices.ModelRejected: ").removeprefix("ModelRejected: ")
                for l in str(report.longreprtext).splitlines() if l.startswith("E ")]
        detail = errs[0].removeprefix("AssertionError: ") if errs else (str(report.longreprtext).strip().splitlines() or [""])[-1]
    _rows.append([SUITE, matrix, callspec, outcome, detail])


def pytest_sessionfinish(session):
    out = Path(os.environ.get("RESULTS_DIR") or Path(__file__).resolve().parents[1] / "results")
    out.mkdir(parents=True, exist_ok=True)
    with open(out / f"{SUITE}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["suite", "matrix", "id", "outcome", "detail"])
        w.writerows(_rows)
