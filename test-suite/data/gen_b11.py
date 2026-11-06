#!/usr/bin/env python3
"""Matrix B11 - binding connector ends.

Full cross product: reads x binding naming (named `binding b bind ...`, unnamed `bind ...`)
x end depth (0: own ports, 1: `x.p`, 2: `m.u1.p`) x location (L2, L3, L6).

Reads are those of B10 (see its notes). An unnamed binding has no qualified name, so it is
located with `unnamed`: the index-th unnamed member of that metaclass declared in `element`
(declaration order), visible in the last element of `through` when one is given.
"""
from genlib import Matrix

READS = ["endCount", "endReferences", "sourceFeature", "targetFeature", "relatedFeature"]
READ_COL = {"endCount": "can count ends", "endReferences": "can get end references",
            "sourceFeature": "can get sourceFeature", "targetFeature": "can get targetFeature",
            "relatedFeature": "can get relatedFeature"}
NAMING_COL = {"named": "named binding", "unnamed": "unnamed binding"}
DEPTH_COL = {0: "end depth 0", 1: "end depth 1", 2: "end depth 2"}
LOC_COL = {"L2": "appears in part def", "L3": "read through typing usage", "L6": "read through nested usage chain"}

V = "B11::Vehicle::"
ENDS = {0: ([V + "q"], [V + "r"]),
        1: ([V + "x", "B11::Unit::p"], [V + "y", "B11::Unit::p"]),
        2: ([V + "m", "B11::Pair::u1", "B11::Unit::p"], [V + "n", "B11::Pair::u2", "B11::Unit::p"])}
THROUGH = {"L2": None, "L3": ["B11::vehicle"], "L6": ["B11::fleet", "B11::Fleet::v"]}

m = Matrix("B11", "binding connector ends", "models/B11.sysml",
           list(READ_COL.values()) + list(NAMING_COL.values()) + list(DEPTH_COL.values()) + list(LOC_COL.values()),
           description="Binding connectors, named and unnamed, read for their ends.",
           notes={"reads": "as in B10",
                  "unnamed": "locates an unnamed element: {metaclass, index} among the unnamed members "
                             "of that metaclass declared in `element`, in declaration order",
                  "through": "a path: each element is read as a member visible in the previous one"})
for read in READS:
    for naming in NAMING_COL:
        for depth in DEPTH_COL:
            for loc in LOC_COL:
                src, tgt = ENDS[depth]
                expect = {"endCount": 2, "endReferences": [src, tgt], "sourceFeature": src,
                          "targetFeature": [tgt], "relatedFeature": [src, tgt]}[read]
                marks = {READ_COL[read], NAMING_COL[naming], DEPTH_COL[depth], LOC_COL[loc]}
                if naming == "named":
                    m.add(marks, read, V + f"b{depth}", expect, THROUGH[loc])
                else:
                    m.add(marks, read, "B11::Vehicle", expect, THROUGH[loc],
                          unnamed={"metaclass": "BindingConnector", "index": depth})
m.write("gen_b11.py")
