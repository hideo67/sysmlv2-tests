#!/usr/bin/env python3
"""Matrix C21 - constructor expressions.

Full cross product: reads x constructor variant (send payload without argument, with a feature
reference argument, with a feature chain argument; a feature value with a feature chain
argument) x location (in an action def body, nested in an action usage owned by a part def,
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
"""
from genlib import Matrix

READS = ["exprKind", "instantiatedType", "argumentCount", "argumentReferences", "hasResult", "resultType"]
READ_COL = {"exprKind": "can get kind", "instantiatedType": "can get instantiated type",
            "argumentCount": "can get argument count", "argumentReferences": "can get argument references",
            "hasResult": "has result", "resultType": "can get result type"}
VARIANTS = {  # variant -> (element name, referenced features of the arguments; X = owner of the features)
    "none": ("sendNone", []),
    "ref": ("sendRef", [["X::gain"]]),
    "chain": ("sendChain", [["X::src", "C21::Src::v"]]),
    "value": ("sigValue", [["X::src", "C21::Src::v"]]),
}
VARIANT_COL = {"none": "send payload, no argument", "ref": "send payload, reference argument",
               "chain": "send payload, chain argument", "value": "feature value, chain argument"}
LOC_COL = {"ADEF": "in action def", "AUSE": "nested in action usage in part def", "L3": "read through typing usage"}
LOC = {  # location -> (owner of the element, owner of the referenced features, through)
    "ADEF": ("C21::Emit", "C21::Emit", None),
    "AUSE": ("C21::Emitter::emit", "C21::Emitter", None),
    "L3": ("C21::Emitter::emit", "C21::Emitter", ["C21::emitter", "C21::Emitter::emit"]),
}

m = Matrix("C21", "constructor expressions", "models/C21.sysml",
           list(READ_COL.values()) + list(VARIANT_COL.values()) + list(LOC_COL.values()),
           description="Constructor expressions (`new Sig(...)`) as send payloads and as a feature value, "
                       "read for their instantiated type, arguments and result.",
           notes={"reads": __doc__.split("Reads (")[1].strip(),
                  "through": "a path: each element is read as a member visible in the previous one"})
for read in READS:
    for variant, (name, refs) in VARIANTS.items():
        for loc in LOC_COL:
            element_owner, feature_owner, through = LOC[loc]
            expect = {"exprKind": "ConstructorExpression", "instantiatedType": "C21::Sig",
                      "argumentCount": len(refs),
                      "argumentReferences": [[f.replace("X::", f"{feature_owner}::") for f in r] for r in refs],
                      "hasResult": True, "resultType": "C21::Sig"}[read]
            m.add({READ_COL[read], VARIANT_COL[variant], LOC_COL[loc]}, read, f"{element_owner}::{name}", expect, through)
m.write("gen_c21.py")
