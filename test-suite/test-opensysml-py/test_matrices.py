"""Every matrix in data/cases/*.json against the OpenSysML Python client.

Only the Symbol API is used: it is OpenSysML's element API, the counterpart of the
Pilot's EMF model and sysml-toolkit's ResolvedModel (DISCUSSIONS.md, Step 5 decision).
When the Symbol API has no field for a read, the result is unsupported, and the detail
says whether the standard SysML v2 API & Services query API offers the property; the
query API is consulted for that note only, never for a value.
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
CASES = [(case.get("model", spec["model"]), case) for spec in SPECS for case in spec["cases"]]


class Unsupported(Exception):
    """The API offers no way to obtain this information."""


class ModelRejected(Exception):
    """The MDK reported errors loading the matrix's model: every case of it is an error."""


@lru_cache(maxsize=None)
def load(model_file):
    m = opensysml.loads((DATA / model_file).read_text())
    if not m.ok:
        errors = [f"line {d.start_line}: {d.message}" for d in m.diagnostics if d.severity == "error"]
        raise ModelRejected("model rejected: " + "; ".join(errors[:2]))
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
    for listing in (s.children(), s.parts(), s.attributes(), s.members(inherited=True, library=True)):
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


# Symbol kinds whose words are abbreviated (internal/semantic/symbols/symbol.go): `calc`,
# `enum`, and a binding, which is a BindingConnectorAsUsage.
KIND_WORDS = {"calc": "calculation", "enum": "enumeration"}
KIND_WHOLE = {"bindingUsage": "BindingConnectorAsUsage"}


def metaclass_of(kind):
    """The Symbol kind spelled as the spec metaclass: lower camel case, with `Def` for
    `Definition` and the abbreviations of KIND_WORDS expanded (`calcDef` -> `CalculationDefinition`)."""
    if kind in KIND_WHOLE:
        return KIND_WHOLE[kind]
    for short, full in KIND_WORDS.items():
        if kind.startswith(short) and kind[len(short):len(short) + 1].isupper():
            kind = full + kind[len(short):]
    if kind.endswith("Def"):
        kind += "inition"
    return kind[:1].upper() + kind[1:]


def _multiplicity(m):
    if m is None:
        return None
    lower = m.lower if m.lower != "" else ("0" if m.upper == "*" else m.upper)
    return f"{lower}..{m.upper}"


def no_symbol_field(model, element, prop, what):
    """Unsupported: the Symbol API has no field for `what`. The detail notes whether the
    standard query API offers `prop` (consulted for this note only)."""
    try:
        rows = model.query(scope=[element], select=[prop])
        offered = any(prop in r.properties for r in rows)
    except (opensysml.errors.InvalidRequestError, opensysml.errors.OpenSysMLError):
        offered = False
    note = (f"available through the standard query API ({prop})" if offered
            else "the standard query API does not offer it either")
    return Unsupported(f"no Symbol field for {what}; {note}")


def evaluate(model, check, element, subject):
    """E10: the feature's value from the evaluation API (Evaluate), in its part def's scope
    or with the usage as subject."""
    owner, name = element.rsplit("::", 1)
    try:
        v = model.eval(name, subject=subject) if subject else model.eval(name, context_symbol_id=owner)
    except opensysml.errors.OpenSysMLError as e:
        return f"<evaluation failed: {e}>"
    is_quantity = isinstance(v, opensysml.values.Quantity)
    if check == "evaluatedUnit":
        return v.unit.text if is_quantity else None
    return v.magnitude if is_quantity else v


_instances = {}


def instance_check(model, check, root, path, path2):
    """F10: walk `path` from the object instantiate(root) builds."""
    key = (model.hash, root)
    if key not in _instances:
        try:
            _instances[key] = model.instantiate(root)
        except opensysml.errors.OpenSysMLError as e:
            _instances[key] = f"<instantiation failed: {e}>"
    obj = _instances[key]
    if isinstance(obj, str):
        return obj

    def walk(p):
        cur = obj
        for name in p.split("."):
            if not hasattr(cur, "get"):
                return f"<{name}: not an object>"
            cur = cur.get(name)
            if cur is None:
                return f"<no feature {name}>"
        return cur

    target = walk(path)
    if check == "ownerPath":
        # the object's path through its owners: of every path paths() lists, the
        # first that steps through no connector end (an end reaches the object
        # it references, not one it owns)
        if isinstance(target, str):
            return target

        def through_end(p):
            return any(getattr(model.get(s.feature_symbol_id), "kind", None) == "connectorEnd" for s in p.steps)
        owned = [p.path for p in target.paths() if not through_end(p)]
        return owned[0] if owned else f"<no path to {path} through owners only>"
    if check == "instanceType":
        return getattr(target, "type_symbol_id", target)
    if check == "instanceValue":
        return target
    if check == "instanceCount":
        return len(target) if isinstance(target, (list, tuple)) else (0 if isinstance(target, str) else 1)
    other = walk(path2)
    return getattr(target, "id", "a") == getattr(other, "id", "b")


def do_check(model, check, element, through=None, unnamed=None, via=None, subject=None,
             path=None, path2=None):
    if check in ('instanceType', 'instanceValue', 'instanceCount', 'endIdentity', 'ownerPath'):
        return instance_check(model, check, element, path, path2)
    if check in ("evaluatedValue", "evaluatedUnit"):
        return evaluate(model, check, element, subject)
    if check == "resolve":
        # the Symbol API's one name lookup: get(qualified name)
        s = model.get(element) or model.get(norm(element))
        return s.id if s else None
    if check in ("isComposite", "isReference"):
        raise no_symbol_field(model, element, check, check)
    if check in ('entryKind', 'doKind', 'exitKind', 'isParallel', 'source', 'target', 'triggerPayload', 'guardKind', 'effectKind'):
        prop = {'entryKind': 'entryAction', 'doKind': 'doAction', 'exitKind': 'exitAction', 'isParallel': 'isParallel', 'source': 'source', 'target': 'target', 'triggerPayload': 'triggerAction', 'guardKind': 'guardExpression', 'effectKind': 'effectAction'}[check]
        raise no_symbol_field(model, element, prop, prop)
    # reads the Symbol API has no field for: unsupported, before the element is even looked up
    # (unsupported takes precedence over not being visible)
    NO_FIELD = {"shortName": ("shortName", "the short name"), "owner": ("owner", "the owner"),
                "isIndividual": ("isIndividual", "isIndividual"), "result": ("result", "the result parameter"),
                "subject": ("subjectParameter", "the subject parameter")}
    if check in NO_FIELD:
        raise no_symbol_field(model, element, *NO_FIELD[check])
    if check in ("documentation", "comments", "textualRepresentation"):
        prop = {"documentation": "documentation", "comments": "comment",
                "textualRepresentation": "textualRepresentation"}[check]
        raise no_symbol_field(model, element, prop, check)
    if check == "substates":
        s, _ = _resolve(model, element, through)
        if isinstance(s, str):
            return s
        return sorted(c.name for c in s.children() if c.kind == "stateUsage")
    if check in ("payloadTypes", "sourceOutput", "targetInput"):
        prop = {"payloadTypes": "payloadType", "sourceOutput": "sourceOutputFeature",
                "targetInput": "targetInputFeature"}[check]
        raise no_symbol_field(model, element, prop, f"the flow's {prop}")
    if check in ("sourceFeature", "targetFeature", "relatedFeature"):
        if unnamed:
            raise Unsupported(f"no Symbol field for {check}; the query API cannot address an unnamed element")
        raise no_symbol_field(model, element, check, check)
    if check in ("endNames", "endCount") and not unnamed and _sym(model, element).kind.endswith("Def"):
        raise Unsupported("the Symbol API does not mark the end features of a definition")
    if check == "allSupertypes":
        raise Unsupported("neither the Symbol nor the query API gives the closure of supertypes")
    if check == "annotatedElement":
        raise Unsupported("neither the Symbol nor the query API reports what a metadata usage annotates")
    if check in ("payloadArgument", "senderArgument", "receiverArgument", "assignedFeature"):
        raise Unsupported("the Symbol API reports no arguments of an action")
    if check in ("valueKind", "valueOperator", "valueReferences", "valueText"):
        raise Unsupported("the Symbol API reports a value only as a folded constant, with no expression structure or text")
    if check in ("exprKind", "instantiatedType", "argumentCount", "argumentReferences", "hasResult", "resultType"):
        raise Unsupported("the Symbol API reports neither the arguments of an action nor expression structure, "
                          "so no constructor expression is reachable")
    if check == "isDefault":
        raise Unsupported("neither Symbol nor AttributeFacts tells a default from a bound value")
    if check == "unnamedPartCount":
        # unnamed part usages declared in `element`, among the members the Symbol lists
        if through:
            cur, _ = _resolve(model, through[-1] if isinstance(through, list) else through,
                              through[:-1] if isinstance(through, list) and len(through) > 1 else None)
            if isinstance(cur, str):
                return cur
            listed = [c for c in _visible(cur).values() if norm(c.id).startswith(norm(element) + "::")]
        else:
            listed = _sym(model, element).children()
        return sum(1 for c in listed if c.kind == "partUsage" and not c.name)
    s, owner = _resolve(model, element, through, unnamed)
    if isinstance(s, str):
        return s
    if check == "name":
        return s.name
    if check == "type":
        if s.type_facts is None:
            raise Unsupported("no type_facts")
        # the derived Feature::type, most specific first (resolved_id is the typing as written)
        return s.type_facts.types[0].id if s.type_facts.types else ""
    if check in ("specializations", "subsettedFeatures"):
        # OpenSysML's Specialization.kind spelled as the spec metaclass
        kinds = {"typing": "FeatureTyping", "subsets": "Subsetting", "redefines": "Redefinition",
                 "references": "ReferenceSubsetting", "specializes": "Subclassification"}
        specs = [[kinds.get(sp.kind, sp.kind), sp.target_id] for sp in s.specializations]
        if check == "specializations":
            return sorted(specs)
        return sorted(t for k, t in specs if k in ("Subsetting", "Redefinition", "ReferenceSubsetting"))
    if check == "types":
        if s.type_facts is None:
            raise Unsupported("no type_facts")
        # the derived Feature::type (resolved_id is the typing as written)
        return sorted(t.id for t in s.type_facts.types)
    if check == "idRoundTrip":
        again = model.get(s.id)
        return again is not None and again.id == s.id
    if check == "directGenerals":
        return sorted(sp.target_id for sp in s.specializations if sp.kind == "specializes")
    if check == "ownedFeatureNames":
        return sorted(c.name for c in s.children() if not c.kind.endswith("Def"))
    if check == "inheritedFeatureNames":
        # members the Symbol lists (children, parts, attributes) that it does not own
        return sorted(c.name for c in _visible(s).values() if not norm(c.id).startswith(norm(s.id) + "::"))
    if check == "redefinitions":
        return sorted([c.id, sp.target_id] for c in s.children() for sp in c.specializations if sp.kind == "redefines")
    if check in ("metadataDefs", "metadataValue"):
        # annotations an element lists: its metadata-usage children
        symbols = [c for c in s.children() if c.kind == "metadataUsage"]
        if check == "metadataDefs":
            return sorted({c.type_facts.resolved_id for c in symbols if c.type_facts})
        if not symbols:
            return f"<no annotation of {s.id} readable as a Symbol>"
        facts = {f.name: f.value for f in symbols[0].attribute_facts()}
        return facts.get("severity")
    if check == "kind":
        return metaclass_of(s.kind)
    if check in ("isAbstract", "isVariation"):
        # Symbol metadata carries `abstract` / `variation: true` when they hold, nothing otherwise
        return s.metadata.get("abstract" if check == "isAbstract" else "variation") == "true"
    if check == "referenceTarget":
        if via == "type":
            return s.type_facts.resolved_id if s.type_facts else None
        targets = [sp.target_id for sp in s.specializations if sp.kind == "subsets"]
        return targets[0] if targets else None
    if check == "parameters":
        # members the Symbol lists that carry a direction in their metadata
        return sorted([c.metadata["direction"], c.name] for c in _visible(s).values() if "direction" in c.metadata)
    if check == "variants":
        # variant usages carry `variant: true` in their metadata
        return sorted(c.name for c in s.children() if c.metadata.get("variant") == "true")
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
        actual = do_check(load(model_file), case["check"], case["element"], case.get("through"), case.get("unnamed"),
                          case.get("via"), case.get("subject"), case.get("path"), case.get("path2"))
    except Unsupported as e:
        pytest.skip(f"UNSUPPORTED: {e}")
    ok = actual == case["expect"] or actual in case.get("accept", [])
    assert ok, f"{case['check']} {case['element']}: got {actual!r}, want {case['expect']!r}"
