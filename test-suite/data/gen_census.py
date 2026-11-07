#!/usr/bin/env python3
"""Derived-property census: the property list every census adapter reads.

Reads the Pilot Implementation's metamodel, org.omg.sysml/model/SysML.ecore of
the cloned Pilot (KerML and SysML in one package), and writes
data/census/derived-properties.json:

  properties   "DefiningClass::name" -> {"many", "type"} for every structural
               feature the ecore marks derived="true"
  metaclasses  every concrete metaclass -> the keys of the derived properties
               it carries, its own and inherited (through eSuperTypes), sorted
  corpora      corpus name -> the .sysml files (paths relative to test-suite/),
               loaded together as one model; expanded from corpusPatterns, less the
               files in excluded (a top-level package another file already declares)

A census adapter loads each corpus into one model, walks every element of it
(owned relationships and their owned related elements, from each document's
root namespace) and, for every derived property the element's metaclass carries,
asks the MDK for the value: non-empty, empty, or not answered. The census report
(census_report.py) tabulates the counts per property and MDK.

Regenerate after updating the Pilot clone: python3 data/gen_census.py
"""
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
PILOT = HERE / "../../SysMLv2-Pilot-Implementation"
ECORE = PILOT / "org.omg.sysml/model/SysML.ecore"
OUT = HERE / "census/derived-properties.json"
XSI = "{http://www.w3.org/2001/XMLSchema-instance}type"

CORPORA = {
    # the matrices' models (data/models): small, each aimed at a few reads
    "matrix-models": ["data/models/*.sysml"],
    # the Pilot's example and training models, at the Pilot commit tested
    "pilot-examples": ["../SysMLv2-Pilot-Implementation/sysml/src/examples/**/*.sysml",
                       "../SysMLv2-Pilot-Implementation/sysml/src/training/**/*.sysml"],
}


def ref(s):
    """'#//Feature' -> 'Feature'; 'ecore:EDataType http://...#//String' -> 'String'."""
    return s.rsplit("#//", 1)[-1]


TOKEN = re.compile(r"'(?:[^'\\]|\\.)*'|[A-Za-z_]\w*|<[^>]*>|[{};]|:>>|:>|::>|::|:|.", re.S)
GRAMMAR = PILOT / "org.omg.sysml.xtext/src/org/omg/sysml/xtext/SysML.xtext"
SKIP_STATEMENTS = {"import", "alias", "doc", "comment", "dependency", "rep", "language"}


def top_level_names(src, keywords):
    """The names a document declares at top level: per top-level statement, the first name
    of its head that is not a keyword (a short name in <...> and everything after a ':'
    or ':>' are not the declared name)."""
    src = re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", src, flags=re.S))
    names, depth, head = [], 0, []
    for t in TOKEN.findall(src):
        if t.isspace():
            continue
        if t in "{;":
            if depth == 0 and head and head[0] not in SKIP_STATEMENTS:
                for h in head:
                    if h.startswith(":") or h == "=":
                        break
                    if h.startswith("'") or (h not in keywords and re.fullmatch(r"[A-Za-z_]\w*", h)):
                        names.append(h.strip("'"))
                        break
            head = []
            depth += t == "{"
        elif t == "}":
            depth -= 1
            head = []
        elif depth == 0:
            head.append(t)
    return names


def drop_duplicates(files, suite_dir):
    """files without those declaring a top-level name an earlier file declares, and the
    dropped ones with the reason. One model holds the whole corpus, and two documents
    declaring the same top-level element is a model OpenSysML refuses as a whole (the
    Pilot's training material repeats four of its examples' top-level names)."""
    keywords = set(re.findall(r"'([a-z]+)'", GRAMMAR.read_text(encoding="utf-8")))
    first, kept, dropped = {}, [], {}
    for f in files:
        names = top_level_names((suite_dir / f).read_text(encoding="utf-8"), keywords)
        clash = next((n for n in names if n in first), None)
        if clash:
            dropped[f] = f"declares top-level '{clash}', as {first[clash]} does"
            continue
        for n in names:
            first[n] = f
        kept.append(f)
    return kept, dropped


def main():
    root = ET.parse(ECORE).getroot()
    classes = {}  # name -> (abstract, supertypes, [(feature, many, type)])
    for c in root.findall("eClassifiers"):
        if c.get(XSI) != "ecore:EClass":
            continue
        supers = [ref(s) for s in (c.get("eSuperTypes") or "").split()]
        derived = []
        for f in c.findall("eStructuralFeatures"):
            if f.get("derived") == "true":
                many = f.get("upperBound") == "-1"
                derived.append((f.get("name"), many, ref(f.get("eType", ""))))
        classes[c.get("name")] = (c.get("abstract") == "true", supers, derived)

    properties = {}
    for name, (_, _, derived) in classes.items():
        for feature, many, typ in derived:
            properties[f"{name}::{feature}"] = {"many": many, "type": typ}

    def carried(name, seen):
        if name in seen:
            return set()
        seen.add(name)
        _, supers, derived = classes[name]
        keys = {f"{name}::{f}" for f, _, _ in derived}
        for s in supers:
            keys |= carried(s, seen)
        return keys

    metaclasses = {name: sorted(carried(name, set()))
                   for name, (abstract, _, _) in sorted(classes.items()) if not abstract}

    suite_dir = HERE.parent
    corpora, excluded = {}, {}
    for name, pats in CORPORA.items():
        files = sorted({str(p.relative_to(suite_dir.resolve(), walk_up=True))
                        for pat in pats for p in suite_dir.resolve().glob(pat)})
        corpora[name], excluded[name] = drop_duplicates(files, suite_dir)

    commit = subprocess.run(["git", "-C", str(PILOT), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "source": {"file": "org.omg.sysml/model/SysML.ecore", "pilotCommit": commit,
                   "nsURI": root.get("nsURI")},
        "generator": "data/gen_census.py",
        "corpusPatterns": CORPORA,
        "corpora": corpora,
        "excluded": excluded,
        "properties": dict(sorted(properties.items())),
        "metaclasses": metaclasses,
    }, indent=1) + "\n")
    print(f"{len(properties)} derived properties, {len(metaclasses)} concrete metaclasses -> {OUT}")


if __name__ == "__main__":
    main()
