#!/usr/bin/env python3
"""Print, as JSON, the version of the MDK a test suite exercises.

  ./mdk_version.py <suite>

run-all.sh calls this right after running a suite and saves the output as
results/<suite>.version.json, so the versions recorded are those of the run.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
JDK21 = os.environ.get("JDK21", "/usr/lib/jvm/java-21-openjdk-amd64")


def sh(*cmd, cwd=None):
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60)
        return (out.stdout or out.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def git(repo, *args):
    return sh("git", "-C", str(repo), *args)


def repo_info(repo):
    status = git(repo, "status", "--porcelain", "--untracked-files=no")
    changed = [line.split(maxsplit=1)[1] for line in status.splitlines() if line.strip()]
    return {
        "repo": git(repo, "remote", "get-url", "origin"),
        "branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
        "describe": git(repo, "describe", "--tags", "--always"),
        "commit": git(repo, "rev-parse", "HEAD"),
        "commit_date": git(repo, "log", "-1", "--format=%cI"),
        "local_changes": changed,
    }


def opensysml_library():
    pin = (ROOT / "OpenSysML" / "scripts" / "pilot-pin.sh").read_text()
    tag = re.search(r'PILOT_TAG="\$\{PILOT_TAG:-([^}]*)\}"', pin)
    rel = re.search(r'PILOT_RELEASE_COMMIT="\$\{PILOT_RELEASE_COMMIT:-([0-9a-f]+)\}"', pin)
    return (f"embedded; SysML-v2-Release {tag.group(1) if tag else '?'} "
            f"({rel.group(1)[:9] if rel else '?'}), per scripts/pilot-pin.sh")


def toolkit_library():
    lib = ROOT / "sysml-toolkit" / "spec-refs" / "SysML-v2-Release"
    return (f"SysML-v2-Release {git(lib, 'describe', '--tags', '--always')} "
            f"({git(lib, 'rev-parse', '--short=9', 'HEAD')}), submodule spec-refs/SysML-v2-Release")


def pilot_version():
    pom = (ROOT / "SysMLv2-Pilot-Implementation" / "pom.xml").read_text()
    m = re.search(r"<revision>([^<]+)</revision>", pom)
    return m.group(1) if m else "?"


SUITES = {
    "opensysml-py": dict(
        mdk="OpenSysML", dir="OpenSysML",
        api="Python client (client/python), Symbol API, over sysml-grpc built from this commit",
        library=opensysml_library,
        toolchain=lambda: sh(str(HERE / "test-opensysml-py" / ".venv" / "bin" / "python"), "--version")),
    "opensysml-go": dict(
        mdk="OpenSysML", dir="OpenSysML",
        api="Go API (client/opensysml) in process, Symbol API",
        library=opensysml_library,
        toolchain=lambda: sh("go", "version")),
    "opensysml-rs": dict(
        mdk="OpenSysML", dir="OpenSysML",
        api="Rust client (client/rust), Symbol API, over sysml-grpc built from this commit",
        library=opensysml_library,
        toolchain=lambda: sh("rustc", "--version", cwd=HERE / "test-opensysml-rs")),
    "sysml-toolkit-rs": dict(
        mdk="sysml-toolkit", dir="sysml-toolkit",
        api="Rust crate sysmlv2-parser, ResolvedModel compatibility reader (element_properties, "
            "derived), closure policy with implied heritage",
        library=toolkit_library,
        toolchain=lambda: sh("rustc", "--version", cwd=HERE / "test-sysml-toolkit-rs")),
    "sysml-toolkit-rs-checked": dict(
        mdk="sysml-toolkit", dir="sysml-toolkit",
        api="Rust crate sysmlv2-parser, ResolvedModel checked reader (property), "
            "closure policy with implied heritage",
        library=toolkit_library,
        toolchain=lambda: sh("rustc", "--version", cwd=HERE / "test-sysml-toolkit-rs")),
    "pilot-java": dict(
        mdk="SysML v2 Pilot Implementation", dir="SysMLv2-Pilot-Implementation",
        api=f"EMF model (org.omg.sysml.lang.sysml) via SysMLInteractive, build {pilot_version()}",
        library=lambda: f"sysml.library of the tested commit ({pilot_version()})",
        toolchain=lambda: sh(f"{JDK21}/bin/java", "-version").splitlines()[0]),
}


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in SUITES:
        sys.exit(f"usage: {sys.argv[0]} <{'|'.join(SUITES)}>")
    suite = sys.argv[1]
    s = SUITES[suite]
    info = {"suite": suite, "mdk": s["mdk"], **repo_info(ROOT / s["dir"]),
            "api": s["api"], "library": s["library"](), "toolchain": s["toolchain"](),
            "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "test_suite_commit": git(ROOT, "rev-parse", "HEAD"),
            "test_suite_local_changes": bool(git(ROOT, "status", "--porcelain", "--untracked-files=no"))}
    print(json.dumps(info, indent=1))


main()
