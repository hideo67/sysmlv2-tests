#!/usr/bin/env python3
"""Matrix A20 - attribute usages: the full cross product of
(what is read) x (where the attribute appears) x (variant of the attribute).

Reads are the spec properties, taken literally:
  name          Element::name (effective name; a redefining feature without a declared name has the redefined one's)
  type          first of Feature::type (derived; includes types inherited through redefinition)
  multiplicity  Type::multiplicity, the owned Multiplicity only, as "lower..upper" (null if none is owned)
  value         literal value of the owned FeatureValue (null if none is owned)
  isDefault     FeatureValue::isDefault of the owned FeatureValue (null if none is owned)
"""
from genlib import Matrix

READS = ["name", "type", "multiplicity", "value", "isDefault"]
READ_COL = {"name": "can read name", "type": "can get type", "multiplicity": "can get multiplicity",
            "value": "can get value", "isDefault": "can tell default"}
LOCS = ["L1", "L2", "L3", "L4", "L5"]
LOC_COL = {"L1": "appears in package", "L2": "appears in part def", "L3": "read through typing usage",
           "L4": "read through usage of specialized def", "L5": "redefined in usage"}
VARS = ["plain", "bound", "dflt", "multi"]
VAR_COL = {"plain": "no value", "bound": "bound value", "dflt": "default value", "multi": "multiplicity range"}

REAL, INT = "ScalarValues::Real", "ScalarValues::Integer"
# variant -> (type, multiplicity, value, isDefault) as declared in package and in Vehicle
DECLARED = {"plain": (REAL, "1..1", None, None), "bound": (REAL, "1..1", 1.5, False),
            "dflt": (REAL, "1..1", 2.5, True), "multi": (INT, "2..4", None, None)}
# variant -> same, for the redefining feature in `tuned`
REDEFINED = {"plain": (REAL, None, 3.5, False), "bound": (REAL, None, None, None),
             "dflt": (REAL, None, 5.5, False), "multi": (INT, "3..3", None, None)}


def element(loc, var):
    return {"L1": (f"A20::{var}", None), "L2": (f"A20::Vehicle::{var}", None),
            "L3": (f"A20::Vehicle::{var}", "A20::vehicle"), "L4": (f"A20::Vehicle::{var}", "A20::truck"),
            "L5": (f"A20::tuned::{var}", None)}[loc]


m = Matrix("A20", "attribute usages", "models/A20.sysml",
           list(READ_COL.values()) + list(LOC_COL.values()) + list(VAR_COL.values()),
           description="Full cross product of what is read, where the attribute appears, and the variant of the attribute.",
           notes={"reads": __doc__.split("Reads are")[1].strip(),
                  "through": "the member is read as seen from this usage, not from its declaring element",
                  "accept": "alternative values that also count as a pass, with the reason in the generator"})
for read in READS:
    for loc in LOCS:
        for var in VARS:
            typ, mult, value, dflt = (REDEFINED if loc == "L5" else DECLARED)[var]
            expect = {"name": var, "type": typ, "multiplicity": mult, "value": value, "isDefault": dflt}[read]
            el, through = element(loc, var)
            extra = {}
            if loc == "L5" and var == "bound" and read in ("value", "isDefault"):
                # tuned::bound owns no FeatureValue, but it is still bound to 1.5 by the
                # redefined feature's binding: an effective-value answer is accepted too.
                extra["accept"] = [{"value": 1.5, "isDefault": False}[read]]
            m.add({READ_COL[read], LOC_COL[loc], VAR_COL[var]}, read, el, expect, through, **extra)
m.write("gen_a20.py")
