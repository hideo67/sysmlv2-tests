"""Every matrix in data/cases/*.json against the OpenSysML Python client.

Only the main APIs are used: the Symbol API and the query API (DISCUSSIONS.md,
Step 3 decisions). An adapter maps one `check` to those APIs.
"""
import json
import os
from functools import lru_cache
from pathlib import Path

import opensysml
import pytest

DATA = Path(__file__).resolve().parents[1] / "data"
# The service binary is the locally built one, never a downloaded release.
os.environ.setdefault("OPENSYSML_BINARY", str(
    Path(__file__).resolve().parents[2] / "OpenSysML" / "bin" / "sysml-grpc"))

SPECS = [json.loads(p.read_text()) for p in sorted((DATA / "cases").glob("*.json"))]
CASES = [(spec["model"], case) for spec in SPECS for case in spec["cases"]]


class Unsupported(Exception):
    """The API offers no way to obtain this information."""


@lru_cache(maxsize=None)
def load(model_file):
    m = opensysml.loads((DATA / model_file).read_text())
    assert m.ok, m.diagnostics
    return m


def norm(qn):
    """Qualified names compared without quoting: OpenSysML spells `CmdPort::~CmdPort`
    where the textual notation quotes `CmdPort::'~CmdPort'`."""
    return qn.replace("'", "")


def _sym(model, element):
    s = model.get(element) or model.get(norm(element))
    assert s is not None, f"no symbol {element}"
    return s


def _visible(s):
    """Members a Symbol lists: children, parts, attributes (own and inherited)."""
    out = {}
    for listing in (s.children(), s.parts(), s.attributes()):
        out.update({norm(c.id): c for c in listing})
    return out


def _resolve(model, element, through, unnamed=None):
    """The element's Symbol, read through a path of usages when `through` is given.
    Returns (symbol, owner symbol) or (message, None) when not visible."""
    path = [] if not through else [through] if isinstance(through, str) else through
    if unnamed:
        # the index-th unnamed member of the metaclass declared in `element`
        if path:
            cur, _ = _resolve(model, path[-1], path[:-1] or None)
            if isinstance(cur, str):
                return cur, None
            listed = [c for c in _visible(cur).values() if c.id.startswith(norm(element) + "::")]
        else:
            cur = _sym(model, element)
            listed = cur.children()
        found = [c for c in listed if not c.name and unnamed["metaclass"].lower() in c.kind.lower()]
        if len(found) <= unnamed["index"]:
            return f"<unnamed {unnamed['metaclass']} #{unnamed['index']} of {element} not listed>", None
        return found[unnamed["index"]], cur
    if not path:
        return _sym(model, element), None
    cur = _sym(model, path[0])
    for step in path[1:] + [element]:
        nxt = _visible(cur).get(norm(step))
        if nxt is None:
            return f"<{step} not visible through {cur.id}>", None
        owner, cur = cur, nxt
    return cur, owner


def _multiplicity(m):
    if m is None:
        return None
    lower = m.lower if m.lower != "" else ("0" if m.upper == "*" else m.upper)
    return f"{lower}..{m.upper}"


def do_check(model, check, element, through=None, unnamed=None):
    if check in ("isComposite", "isReference"):
        # Symbol has no such flag, and the query API does not know the property.
        try:
            model.query(scope=[element], select=[check])
        except opensysml.errors.InvalidRequestError as e:
            raise Unsupported(f"query API: {e}".split(";")[0])
        raise AssertionError("query accepted the property; extend the adapter")
    if check in ("sourceFeature", "targetFeature", "relatedFeature") and unnamed:
        raise Unsupported("the Symbol API has no connector features, and the query API cannot address an unnamed element")
    if check in ("sourceFeature", "targetFeature", "relatedFeature"):
        # the Symbol API has no such field; try the query API
        try:
            rows = model.query(scope=[element], select=[check])
        except opensysml.errors.InvalidRequestError as e:
            raise Unsupported(f"query API: {e}".split(";")[0])
        raise AssertionError(f"query accepted {check}; extend the adapter: {rows}")
    if check in ("endNames", "endCount") and not unnamed and _sym(model, element).kind.endswith("Def"):
        raise Unsupported("the Symbol API does not mark the end features of a definition")
    if check == "annotatedElement":
        raise Unsupported("neither the Symbol nor the query API reports what a metadata usage annotates")
    if check in ("payloadArgument", "senderArgument", "receiverArgument", "assignedFeature"):
        raise Unsupported("the Symbol API reports no arguments of an action")
    if check in ("valueKind", "valueOperator", "valueReferences", "valueText"):
        raise Unsupported("the Symbol API reports a value only as a folded constant, with no expression structure or text")
    if check == "isDefault":
        raise Unsupported("neither Symbol nor AttributeFacts tells a default from a bound value")
    if check == "unnamedPartCount":
        rows = model.query(scope=[through or element])
        return sum(1 for r in rows if r.type == "PartUsage"
                   and r.properties.get("owner") == element and "name" not in r.properties)
    s, owner = _resolve(model, element, through, unnamed)
    if isinstance(s, str):
        return s
    if check == "name":
        return s.name
    if check == "type":
        if s.type_facts is None:
            raise Unsupported("no type_facts")
        return s.type_facts.resolved_id
    if check in ("metadataDefs", "metadataValue"):
        # annotations an element lists: metadata-usage children (Symbol API), and
        # MetadataUsage rows the query API reports as owned by the element
        symbols = [c for c in s.children() if c.kind == "metadataUsage"]
        rows = [r for r in model.query(scope=[s.id]) if r.type == "MetadataUsage" and r.properties.get("owner") == s.id]
        if check == "metadataDefs":
            types = {c.type_facts.resolved_id for c in symbols if c.type_facts}
            types |= {r.properties["type"] for r in rows if "type" in r.properties}
            return sorted(types)
        if not symbols:
            return f"<no annotation of {s.id} readable as a Symbol>"
        facts = {f.name: f.value for f in symbols[0].attribute_facts()}
        return facts.get("severity")
    if check == "kind":
        # the Symbol kind is the metaclass name in lower camel case
        return s.kind[:1].upper() + s.kind[1:]
    if check == "typeIsConjugated":
        if s.type_facts is None or not s.type_facts.resolved_id:
            return None
        # a conjugated port definition is named "~" + its original's name (SysML spec)
        return _sym(model, s.type_facts.resolved_id).name.startswith("~")
    if check == "direction":
        # the member's direction as the Symbol reports it when listed through the port
        return s.metadata.get("direction")
    if check == "multiplicity":
        return _multiplicity(s.multiplicity)
    if check in ("endCount", "endNames", "endReferences"):
        ends = [c for c in s.children() if c.kind == "connectorEnd"]
        if check == "endCount":
            return len(ends)
        if check == "endNames":
            return [e.name for e in ends]
        # an end's reference is reported, if at all, as a subsets/references specialization
        return [[sp.target_id for sp in e.specializations if sp.kind in ("subsets", "references")] for e in ends]
    if check == "value":
        # a feature's value is reported by its owner's attribute_facts()
        owner = owner or _sym(model, element.rsplit("::", 1)[0])
        facts = {f.name: f for f in owner.attribute_facts()}
        if s.name not in facts:
            return f"<{s.name} not in attribute_facts of {owner.id}>"
        return facts[s.name].value
    raise AssertionError(f"unknown check {check}")


@pytest.mark.parametrize("model_file,case", CASES, ids=[c["id"] for _, c in CASES])
def test_case(model_file, case):
    try:
        actual = do_check(load(model_file), case["check"], case["element"], case.get("through"), case.get("unnamed"))
    except Unsupported as e:
        pytest.skip(f"UNSUPPORTED: {e}")
    ok = actual == case["expect"] or actual in case.get("accept", [])
    assert ok, f"{case['check']} {case['element']}: got {actual!r}, want {case['expect']!r}"
