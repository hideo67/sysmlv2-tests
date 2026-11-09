"""Every matrix in data/cases/*.json against OpenSysML's element properties API
(suite opensysml-py-props).

Every model value comes from `Model.element_properties(element, *names)`, the
GetElementProperties RPC: an element's KerML / SysML metamodel properties read by
their specification names, as the Pilot's EMF model and sysml-toolkit's
`derived(element, "<spec name>")` are read (DISCUSSIONS.md, Step 11). Each read
takes the same route through the abstract syntax as the sysml-toolkit adapter.
The Symbol API is not used; the runtime reads (E10 evaluation, F10 instances) use
the same evaluation and instantiation API as suite opensysml-py.

A property the service reports as not derived is unsupported, with the service's
reason. A property the element's metaclass does not declare reads as empty.
KerML operations are not properties: `allSupertypes()` is unsupported, and the
direction of a feature in an owner (`directionOf()`) is read from the owner's
`input` and `output`, the properties KerML defines by it (DISCUSSIONS.md, Step 19).
"""
import json
from pathlib import Path

import opensysml
import pytest

from test_matrices import Unsupported, evaluate, instance_check, load, norm

DATA = Path(__file__).resolve().parents[1] / "data"
SPECS = [json.loads(p.read_text()) for p in sorted((DATA / "cases").glob("*.json"))]
CASES = [(case.get("model", spec["model"]), case) for spec in SPECS for case in spec["cases"]]

NO_OPERATION = "GetElementProperties reads properties only; KerML operation {} is not served"


class NoId(Exception):
    """The service answered an element reference that carries no id: it cannot be
    read back, and it cannot be told apart from other references without one."""


def need_id(e):
    if not e.id:
        raise NoId(f"{e.metaclass} {e.qualified_name or '(unnamed)'}")
    return e.id


class Api:
    """Property reads of one model, each (element id, property) read once."""

    def __init__(self, model):
        self.model = model
        self._props = {}
        self._found = {}
        self._trees = {}

    def find(self, qn):
        """The element a qualified name (or positional or form id) names, or None."""
        if qn not in self._found:
            found = None
            for name in dict.fromkeys([qn, norm(qn)]):
                try:
                    found = self.model.element_properties(name, "name").element
                    break
                except opensysml.errors.SymbolNotFoundError:
                    continue
            self._found[qn] = found
        return self._found[qn]

    def read(self, e, *names):
        """The ElementProperty entries of `names` for element `e`, fetched together."""
        need_id(e)
        missing = [n for n in names if (e.id, n) not in self._props]
        if missing:
            for p in self.model.element_properties(e.id, *missing):
                self._props[(e.id, p.name)] = p
        out = []
        for n in names:
            p = self._props[(e.id, n)]
            if p.unsupported and p.defining_class:
                raise Unsupported(f"{n} of {e.metaclass}: {p.unsupported}")
            out.append(p)
        return out

    def elements(self, e, name):
        return self.read(e, name)[0].elements

    def element(self, e, name):
        els = self.elements(e, name)
        return els[0] if els else None

    def scalar(self, e, name):
        p = self.read(e, name)[0]
        return p.value if p.values else None

    @staticmethod
    def qn(e):
        return e.qualified_name if e is not None and e.qualified_name else None

    def name(self, e):
        return self.scalar(e, "name")

    def visible_features(self, t):
        """Everything visible in a type: the union of `feature`, `ownedFeature`,
        `inheritedFeature` and `member`, and the members of its inherited memberships."""
        out = {}
        for p in self.read(t, "feature", "ownedFeature", "inheritedFeature", "member"):
            for f in p.elements:
                out.setdefault(need_id(f), f)
        for ms in self.elements(t, "inheritedMembership"):
            try:
                members = self.elements(ms, "memberElement")
            except opensysml.errors.ConversionError:
                # a library membership the service lists but cannot read back
                # (DISCUSSIONS.md, Step 11); its member is usually also an inheritedFeature
                continue
            for f in members:
                out.setdefault(need_id(f), f)
        return list(out.values())

    def chain_form(self, f):
        """A referenced feature as its chainingFeatures' qualified names (one if not a chain)."""
        chain = self.elements(f, "chainingFeature")
        return [self.qn(p) for p in (chain or [f])]

    def value_expr(self, e):
        """The value expression of the feature's owned FeatureValue."""
        fv = next((m for m in self.elements(e, "ownedMembership") if m.metaclass == "FeatureValue"), None)
        return self.element(fv, "value") if fv else None

    def references(self, x):
        """Referenced features of an expression, left to right, each in chain form."""
        if x.metaclass == "FeatureReferenceExpression":
            f = self.element(x, "referent")
            return [self.chain_form(f)] if f else []
        if x.metaclass == "FeatureChainExpression":
            args = self.elements(x, "argument")
            chain = []
            if args:
                refs = self.references(args[0])
                chain = list(refs[-1]) if refs else []
            t = self.element(x, "targetFeature")
            if t:
                chain += self.chain_form(t)
            return [chain]
        out = []
        for a in self.elements(x, "argument"):
            out += self.references(a)
        return out

    def tree(self, root):
        """Every element owned, directly or not, by the root package `root`."""
        if root not in self._trees:
            out, todo, seen = [], [self.find(root)], set()
            while todo:
                cur = todo.pop()
                if cur is None or need_id(cur) in seen:
                    continue
                seen.add(cur.id)
                out.append(cur)
                todo += reversed(self.elements(cur, "ownedElement"))
            self._trees[root] = out
        return self._trees[root]

    def annotating(self, e, metaclass):
        """Elements of `metaclass` in e's root package whose annotatedElement includes e."""
        root = (e.qualified_name or "").split("::")[0]
        return [x for x in self.tree(root) if x.metaclass == metaclass
                and any(a.id == e.id for a in self.elements(x, "annotatedElement"))]

    def body(self, c):
        return (self.scalar(c, "body") or "").strip()

    def literal(self, x):
        if x.metaclass == "LiteralInfinity":
            return "*"
        return self.scalar(x, "value")

    def implied(self, r):
        return self.scalar(r, "isImplied") is True


_apis = {}


def api_of(model):
    if model.hash not in _apis:
        _apis[model.hash] = Api(model)
    return _apis[model.hash]


def through_path(through):
    return [] if not through else [through] if isinstance(through, str) else list(through)


def do_check(model, case):
    check, element = case["check"], case["element"]
    path = through_path(case.get("through"))
    if check in ("instanceType", "instanceValue", "instanceCount", "endIdentity", "ownerPath"):
        return instance_check(model, check, element, case.get("path"), case.get("path2"))
    if check in ("evaluatedValue", "evaluatedUnit"):
        return evaluate(model, check, element, case.get("subject"))
    api = api_of(model)
    if check == "resolve":
        # the element id of GetElementProperties is resolved as a qualified name; a name
        # that resolves to a Membership (an alias) stands for its memberElement
        found = api.find(element)
        if found is not None and found.metaclass.endswith("Membership"):
            found = api.element(found, "memberElement")
        return api.qn(found)
    if check == "allSupertypes":
        raise Unsupported(NO_OPERATION.format("Type::allSupertypes()"))
    if check == "valueText":
        raise Unsupported("no property holds an expression's source text")
    if check == "unnamedPartCount":
        scope = api.find(path[0] if path else element)
        if scope is None:
            return f"<no element {path[0] if path else element}>"
        members = api.visible_features(scope) if path else api.elements(scope, "ownedMember")
        return sum(1 for m in members if m.metaclass == "PartUsage" and api.name(m) is None
                   and api.qn(api.element(m, "owningNamespace")) == element)

    # the element, read through each step of the path as a member visible in the previous one
    owner = None
    unnamed = case.get("unnamed")
    if unnamed:
        if not path:
            scope = api.find(element)
            if scope is None:
                return f"<no element {element}>"
            members = api.elements(scope, "ownedMember")
        else:
            scope = api.find(path[0])
            for step in path[1:]:
                scope = next((f for f in api.visible_features(scope) if norm(api.qn(f) or "") == norm(step)), None)
                if scope is None:
                    return f"<{step} not visible>"
            members = api.visible_features(scope)
        found = [m for m in members if api.name(m) is None and unnamed["metaclass"] in m.metaclass
                 and api.qn(api.element(m, "owningNamespace")) == element]
        owner = scope
        if len(found) <= unnamed["index"]:
            return f"<unnamed {unnamed['metaclass']} #{unnamed['index']} of {element} not listed>"
        e = found[unnamed["index"]]
    elif not path:
        e = api.find(element)
        if e is None:
            raise Unsupported(f"no element {element}")
    else:
        cur = api.find(path[0])
        assert cur is not None, f"no element {path[0]}"
        for step in path[1:] + [element]:
            nxt = next((f for f in api.visible_features(cur) if norm(api.qn(f) or "") == norm(step)), None)
            if nxt is None:
                return f"<{step} not visible through {api.qn(cur)}>"
            owner, cur = cur, nxt
        e = cur

    def qn_of(prop, x=e):
        return api.qn(api.element(x, prop))

    if check == "name":
        return api.name(e)
    if check == "kind":
        return e.metaclass
    if check == "type":
        return qn_of("type")
    if check in ("isComposite", "isReference", "shortName", "isAbstract", "isVariation",
                 "isIndividual", "isParallel"):
        return api.scalar(e, check)
    if check == "documentation":
        return sorted(api.body(d) for d in api.elements(e, "documentation"))
    if check == "comments":
        return sorted(api.body(c) for c in api.annotating(e, "Comment"))
    if check == "textualRepresentation":
        return sorted(([api.scalar(r, "language"), api.body(r)] for r in api.elements(e, "textualRepresentation")),
                      key=json.dumps)
    if check in ("entryKind", "doKind", "exitKind", "guardKind", "effectKind"):
        prop = {"entryKind": "entryAction", "doKind": "doAction", "exitKind": "exitAction",
                "guardKind": "guardExpression", "effectKind": "effectAction"}[check]
        a = api.element(e, prop)
        return a.metaclass if a else None
    if check == "substates":
        return sorted(api.name(f) or "" for f in api.elements(e, "ownedFeature") if f.metaclass == "StateUsage")
    if check in ("source", "target"):
        return qn_of(check)
    if check == "triggerPayload":
        acc = api.element(e, "triggerAction")
        p = api.element(acc, "payloadParameter") if acc else None
        return qn_of("type", p) if p else None
    if check == "payloadTypes":
        return sorted(api.qn(t) for t in api.elements(e, "payloadType"))
    if check in ("sourceOutput", "targetInput"):
        f = api.element(e, "sourceOutputFeature" if check == "sourceOutput" else "targetInputFeature")
        target = None
        for r in api.elements(f, "ownedRedefinition") if f else []:
            target = qn_of("redefinedFeature", r) or target
        return target
    if check == "referenceTarget":
        if case.get("via") == "type":
            return qn_of("type")
        for r in api.elements(e, "ownedSubsetting"):
            if not api.implied(r) and api.element(r, "subsettedFeature"):
                return qn_of("subsettedFeature", r)
        return None
    if check in ("specializations", "subsettedFeatures"):
        out = []
        for r in api.elements(e, "ownedSpecialization" if check == "specializations" else "ownedSubsetting"):
            if api.implied(r):
                continue
            prop = {"FeatureTyping": "type", "ConjugatedPortTyping": "type", "Subsetting": "subsettedFeature",
                    "Redefinition": "redefinedFeature", "ReferenceSubsetting": "referencedFeature",
                    "Subclassification": "superclassifier"}.get(r.metaclass, "general")
            general = qn_of(prop, r) or qn_of("general", r)
            if check == "specializations":
                out.append([r.metaclass, general])
            elif general is not None:
                out.append(general)
        return sorted(out, key=json.dumps)
    if check == "types":
        return sorted(api.qn(t) for t in api.elements(e, "type"))
    if check == "owner":
        return qn_of("owningNamespace")
    if check == "idRoundTrip":
        again = api.model.element_properties(need_id(e), "name").element
        return again.id == e.id
    if check == "directGenerals":
        return sorted(qn_of("superclassifier", r) for r in api.elements(e, "ownedSubclassification")
                      if not api.implied(r))
    if check in ("ownedFeatureNames", "inheritedFeatureNames"):
        prop = "ownedFeature" if check == "ownedFeatureNames" else "inheritedFeature"
        return sorted(api.name(f) or "" for f in api.elements(e, prop))
    if check == "redefinitions":
        return sorted(([api.qn(f), qn_of("redefinedFeature", r)] for f in api.elements(e, "ownedFeature")
                       for r in api.elements(f, "ownedRedefinition")), key=json.dumps)
    if check == "parameters":
        # each directed feature's own direction (directionOf is an operation)
        return sorted(([api.scalar(f, "direction"), api.name(f) or ""] for f in api.elements(e, "directedFeature")),
                      key=json.dumps)
    if check in ("result", "subject"):
        p = api.element(e, "result" if check == "result" else "subjectParameter")
        return api.name(p) if p else None
    if check == "variants":
        return sorted(api.name(v) or "" for v in api.elements(e, "variant"))
    if check in ("metadataDefs", "metadataValue", "annotatedElement"):
        mus = api.annotating(e, "MetadataUsage")
        if check == "metadataDefs":
            return sorted(qn_of("metadataDefinition", mu) for mu in mus)
        if not mus:
            return f"<no annotation of {element} found>"
        if check == "annotatedElement":
            return [api.qn(a) for a in api.elements(mus[0], "annotatedElement")]
        v = None
        for f in api.elements(mus[0], "ownedFeature"):
            if api.name(f) == "severity":
                x = api.value_expr(f)
                if x:
                    v = api.literal(x)
        return v
    if check in ("payloadArgument", "senderArgument", "receiverArgument"):
        x = api.element(e, check)
        return api.references(x) if x else None
    if check == "assignedFeature":
        f = api.element(e, "referent")
        return api.chain_form(f) if f else None
    if check in ("exprKind", "instantiatedType", "argumentCount", "argumentReferences", "hasResult", "resultType"):
        x = api.element(e, "payloadArgument") if e.metaclass == "SendActionUsage" else api.value_expr(e)
        if x is None:
            return None
        if check == "exprKind":
            return x.metaclass
        if check == "instantiatedType":
            return qn_of("instantiatedType", x)
        if check == "argumentCount":
            return len(api.elements(x, "argument"))
        if check == "argumentReferences":
            return [r for a in api.elements(x, "argument") for r in api.references(a)]
        r = api.element(x, "result")
        if check == "hasResult":
            return r is not None
        return qn_of("type", r) if r else None
    if check in ("valueKind", "valueOperator", "valueReferences"):
        x = api.value_expr(e)
        if x is None:
            return None
        if check == "valueKind":
            return x.metaclass
        if check == "valueOperator":
            return api.scalar(x, "operator")   # empty when the metaclass declares no operator
        return api.references(x)
    if check in ("endCount", "endNames"):
        ends = api.elements(e, "endFeature" if e.metaclass.endswith("Definition") else "connectorEnd")
        return len(ends) if check == "endCount" else [api.name(x) for x in ends]
    if check == "endReferences":
        out = []
        for end in api.elements(e, "connectorEnd"):
            rs = api.element(end, "ownedReferenceSubsetting")
            f = api.element(rs, "referencedFeature") if rs else None
            out.append(api.chain_form(f) if f else None)
        return out
    if check == "sourceFeature":
        f = api.element(e, "sourceFeature")
        return api.chain_form(f) if f else None
    if check in ("targetFeature", "relatedFeature"):
        return [api.chain_form(f) for f in api.elements(e, check)]
    if check == "typeIsConjugated":
        t = api.element(e, "type")
        return t.metaclass == "ConjugatedPortDefinition" if t else None
    if check == "direction":
        if owner is not None:
            # Type::directionOf(feature) is an operation; the properties defined by it are
            # Type::input and Type::output (KerML 8.3.3.1): in, out or both is inout
            ins = any(f.id == e.id for f in api.elements(owner, "input"))
            outs = any(f.id == e.id for f in api.elements(owner, "output"))
            return {(True, False): "in", (False, True): "out", (True, True): "inout"}.get((ins, outs))
        return api.scalar(e, "direction")
    if check == "multiplicity":
        m = api.element(e, "multiplicity")
        if m is None:
            return None
        u = api.element(m, "upperBound")
        upper = api.literal(u) if u else None
        lo = api.element(m, "lowerBound")
        lower = api.literal(lo) if lo else (0 if upper == "*" else upper)
        return f"{lower}..{upper}"
    if check in ("value", "isDefault"):
        fv = next((m for m in api.elements(e, "ownedMembership") if m.metaclass == "FeatureValue"), None)
        if fv is None:
            return None
        if check == "isDefault":
            return api.scalar(fv, "isDefault")
        x = api.element(fv, "value")
        return api.literal(x) if x else None
    raise AssertionError(f"unknown check {check}")


@pytest.mark.parametrize("model_file,case", CASES, ids=[c["id"] for _, c in CASES])
def test_case(model_file, case):
    try:
        actual = do_check(load(model_file), case)
    except Unsupported as e:
        pytest.skip(f"UNSUPPORTED: {e}")
    except opensysml.errors.ConversionError as e:
        # the service named an element in an answer and cannot read it back
        actual = f"<unreadable element: {e}>"
    except NoId as e:
        actual = f"<element without id: {e}>"
    ok = actual == case["expect"] or actual in case.get("accept", [])
    assert ok, f"{case['check']} {case['element']}: got {actual!r}, want {case['expect']!r}"
