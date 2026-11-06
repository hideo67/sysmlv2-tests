#!/usr/bin/env python3
"""Matrix E10 - static evaluation of feature values.

Full cross product: reads x expression (literal, arithmetic, feature reference, feature chain,
conditional, comparison, string, quantity with a unit) x context (DEF the part def itself,
L3 a typing usage `vehicle : Vehicle`, L5 a usage `tuned` that redefines `lit` = 0.5 and
`engine.power` = 200.0, so the features that depend on them evaluate differently there).

Each MDK is driven through its evaluation API, not its element API: the Pilot's
Expression::evaluate(target) on the feature's value expression with the context as target;
sysml-toolkit's evaluate (DEF) and evaluate_qualified("E10::tuned::refd") (a usage path sets
the context); OpenSysML's Evaluate with the context symbol (DEF) or the usage as subject.
Reads:
  evaluatedValue  the evaluated value: a number, boolean or string; for a quantity, its
                  magnitude in the unit written
  evaluatedUnit   the unit of a quantity value as written ("kg"); null for a value that is not
                  a quantity
"""
from genlib import Matrix

READ_COL = {"evaluatedValue": "can evaluate value", "evaluatedUnit": "can get unit"}
EXPR_COL = {"lit": "literal", "arith": "arithmetic", "refd": "feature reference", "chain": "feature chain",
            "cond": "conditional", "flag": "comparison", "label": "string", "mass": "quantity with unit"}
CTX_COL = {"DEF": "in part def", "L3": "in typing usage", "L5": "in usage with redefinitions"}
SUBJECT = {"DEF": None, "L3": "E10::vehicle", "L5": "E10::tuned"}
VALUE = {
    "DEF": {"lit": 2.5, "arith": 6.5, "refd": 2.5, "chain": 100.0, "cond": 1.0, "flag": True, "label": "pump", "mass": 1500.0},
    "L5": {"lit": 0.5, "arith": 6.5, "refd": 0.5, "chain": 200.0, "cond": 0.0, "flag": False, "label": "pump", "mass": 1500.0},
}
VALUE["L3"] = VALUE["DEF"]

m = Matrix("E10", "static evaluation of feature values", "models/E10.sysml",
           list(READ_COL.values()) + list(EXPR_COL.values()) + list(CTX_COL.values()),
           description="Feature values evaluated in a definition, a usage, and a usage with redefinitions.",
           notes={"reads": __doc__.split("Reads:")[1].strip(),
                  "subject": "the usage the feature is evaluated in; absent: evaluated in its part def"})
for read in READ_COL:
    for expr in EXPR_COL:
        for ctx in CTX_COL:
            expect = VALUE[ctx][expr] if read == "evaluatedValue" else ("kg" if expr == "mass" else None)
            extra = {"subject": SUBJECT[ctx]} if SUBJECT[ctx] else {}
            m.add({READ_COL[read], EXPR_COL[expr], CTX_COL[ctx]}, read, f"E10::Vehicle::{expr}", expect, **extra)
m.write("gen_e10.py")
