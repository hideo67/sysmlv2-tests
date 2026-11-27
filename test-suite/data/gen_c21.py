#!/usr/bin/env python3
"""Matrix C21 - constructor and type operator expressions.

Full cross product: reads x constructor variant (send payload without argument, with a feature
reference argument, with a feature chain argument; a feature value with a feature chain
argument; an item's feature value constructing a library type, ShapeItems::Triangle, in its own
model C21-library.sysml, package C21Lib, through the case field `model`) x location (in an action def body, nested in an action usage owned by a part def,
read through a typing usage of that part def).

Reads (the constructor is the payloadArgument of the send action, or the value expression of
the attribute's owned FeatureValue; arguments are compared as in C10, as the referenced
features of their expressions, each in chain form):
  exprKind            metaclass of the constructor (ConstructorExpression)
  instantiatedType    qualified name of InstantiationExpression::instantiatedType
  argumentCount       number of InstantiationExpression::argument
  argumentReferences  referenced features of the arguments, collected left to right
  hasResult           whether Expression::result is present (multiplicity 1 in KerML)
  resultType          qualified name of the first of the result parameter's Feature::type
  exprFunction        qualified name of Expression::function
Added later, appended after the original cases to keep their IDs: the read exprFunction (for the
four original variants), then the variant library (for every read), then the type operators
(for every read): an item feature value `original as Command` (a cast), `all Command`, and an
attribute feature value `original istype Command`. By the grammar the type operand of `as` and
`all` is the result parameter (TypeResultMember, a ReturnParameterMembership), so their result
is typed by P::Command; that of `istype` is an input (TypeReferenceMember), and its result is the
library function's Boolean. Their instantiatedType is the operator's function, and the type
operand is not an argument. Then the feature chain operator (for every read): an attribute feature
value `src.v`, a FeatureChainExpression (an OperatorExpression with operator "."). Its one argument
is the source expression (the target feature is not an argument), its function is
ControlFunctions::'.' (the unquoted spelling is accepted), and its result is typed by the chain's target feature's type, ScalarValues::Real:
by checkFeatureChainExpressionResultSpecialization (KerML semantics, Control Functions) the result subsets the
expression's feature chain, so the result's Feature::type includes the types of that chain.
"""
from genlib import Matrix

READS = ["exprKind", "instantiatedType", "argumentCount", "argumentReferences", "hasResult", "resultType"]
READ_COL = {"exprKind": "can get kind", "instantiatedType": "can get instantiated type",
            "argumentCount": "can get argument count", "argumentReferences": "can get argument references",
            "hasResult": "has result", "resultType": "can get result type",
            "exprFunction": "can get function"}
VARIANTS = {  # variant -> (element name, referenced features of the arguments; X = owner of the features)
    "none": ("sendNone", []),
    "ref": ("sendRef", [["X::gain"]]),
    "chain": ("sendChain", [["X::src", "C21::Src::v"]]),
    "value": ("sigValue", [["X::src", "C21::Src::v"]]),
}
# type operator -> (element name, referenced features of the arguments, function, result type)
OPERATORS = {
    "cast": ("narrowed", [["X::original"]], "BaseFunctions::as", "C21::Command"),
    "all": ("allCommands", [], "BaseFunctions::all", "C21::Command"),
    "istype": ("tested", [["X::original"]], "BaseFunctions::istype", "ScalarValues::Boolean"),
}
CHAIN_OP = ("chained", [["X::src"]], "ControlFunctions::'.'", "ScalarValues::Real")
LIBRARY = ("shape", [["X::src", "C21Lib::Src::l"], ["X::src", "C21Lib::Src::w"], ["X::src", "C21Lib::Src::x"]])
VARIANT_COL = {"none": "send payload, no argument", "ref": "send payload, reference argument",
               "chain": "send payload, chain argument", "value": "feature value, chain argument",
               "library": "library type, item feature value",
               "cast": "cast (as), item feature value", "all": "all instances (all), item feature value",
               "istype": "classification test (istype), attribute feature value",
               "chainop": "feature chain (.), attribute feature value"}
LOC_COL = {"ADEF": "in action def", "AUSE": "nested in action usage in part def", "L3": "read through typing usage"}
LOC = {  # location -> (owner of the element, owner of the referenced features, through)
    "ADEF": ("C21::Emit", "C21::Emit", None),
    "AUSE": ("C21::Emitter::emit", "C21::Emitter", None),
    "L3": ("C21::Emitter::emit", "C21::Emitter", ["C21::emitter", "C21::Emitter::emit"]),
}

m = Matrix("C21", "constructor expressions", "models/C21.sysml",
           list(READ_COL.values()) + list(VARIANT_COL.values()) + list(LOC_COL.values()),
           description="Constructor expressions (`new Sig(...)`) as send payloads and as a feature value, "
                       "the type operators `as`, `all` and `istype` and the feature chain operator `.` as feature values, "
                       "read for their instantiated type, arguments and result.",
           notes={"reads": __doc__.split("Reads (")[1].strip(),
                  "model": "a case may name its own model; it overrides the matrix's model for that case",
                  "through": "a path: each element is read as a member visible in the previous one"})
FUNCTION = "Performances::Evaluation"  # the Function typing every ConstructorExpression (Pilot)


def add(read, variant, name, refs, instantiated, kind="ConstructorExpression", function=FUNCTION, result=None,
        **extra):
    for loc in LOC_COL:
        element_owner, feature_owner, through = LOC[loc]
        if "model" in extra:  # the library variant's own model: the same structure in package C21Lib
            element_owner, feature_owner = (s.replace("C21::", "C21Lib::") for s in (element_owner, feature_owner))
            through = [s.replace("C21::", "C21Lib::") for s in through] if through else None
        expect = {"exprKind": kind, "instantiatedType": instantiated,
                  "argumentCount": len(refs),
                  "argumentReferences": [[f.replace("X::", f"{feature_owner}::") for f in r] for r in refs],
                  "hasResult": True, "resultType": result or instantiated, "exprFunction": function}[read]
        accept = {"accept": [expect.replace("'", "")]} if isinstance(expect, str) and "'" in expect else {}
        m.add({READ_COL[read], VARIANT_COL[variant], LOC_COL[loc]}, read, f"{element_owner}::{name}", expect, through,
              **extra, **accept)


for read in READS:
    for variant, (name, refs) in VARIANTS.items():
        add(read, variant, name, refs, "C21::Sig")
for variant, (name, refs) in VARIANTS.items():
    add("exprFunction", variant, name, refs, "C21::Sig")
for read in READS + ["exprFunction"]:
    add(read, "library", *LIBRARY, "ShapeItems::Triangle", model="models/C21-library.sysml")
for read in READS + ["exprFunction"]:
    for variant, (name, refs, function, result) in OPERATORS.items():
        add(read, variant, name, refs, function, kind="OperatorExpression", function=function, result=result)
name, refs, function, result = CHAIN_OP
for read in READS + ["exprFunction"]:
    add(read, "chainop", name, refs, function, kind="FeatureChainExpression", function=function, result=result)
m.write("gen_c21.py")
