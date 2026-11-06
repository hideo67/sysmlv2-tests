#!/usr/bin/env python3
"""Matrix B12 - named connector ends.

B10 with every connector end named (`connect supplier ::> x.p to consumer ::> y.p`), the
form used in the model of OpenSysML issue #1956. Full cross product: reads x connector
kind (connection, interface) x end depth (0: own ports, 1: `x.p`, 2: `m.u1.p`) x location
(L2 owned by part def, L3 through typing usage, L6 through nested usage chain).

Reads are those of B10 (see its notes), plus:
  endNames   names of the connector's ends (Connector::connectorEnd), in order
"""
from genlib import Matrix

READS = ["endCount", "endNames", "endReferences", "sourceFeature", "targetFeature", "relatedFeature"]
READ_COL = {"endCount": "can count ends", "endNames": "can get end names", "endReferences": "can get end references",
            "sourceFeature": "can get sourceFeature", "targetFeature": "can get targetFeature",
            "relatedFeature": "can get relatedFeature"}
KIND_COL = {"connection": "connection", "interface": "interface"}
DEPTH_COL = {0: "end depth 0", 1: "end depth 1", 2: "end depth 2"}
LOC_COL = {"L2": "appears in part def", "L3": "read through typing usage", "L6": "read through nested usage chain"}

V = "B12::Vehicle::"
ENDS = {0: ([V + "q"], [V + "r"]),
        1: ([V + "x", "B12::Unit::p"], [V + "y", "B12::Unit::p"]),
        2: ([V + "m", "B12::Pair::u1", "B12::Unit::p"], [V + "n", "B12::Pair::u2", "B12::Unit::p"])}
THROUGH = {"L2": None, "L3": ["B12::vehicle"], "L6": ["B12::fleet", "B12::Fleet::v"]}

m = Matrix("B12", "named connector ends", "models/B12.sysml",
           list(READ_COL.values()) + list(KIND_COL.values()) + list(DEPTH_COL.values()) + list(LOC_COL.values()),
           description="Connector usages with named ends, read for their ends.",
           notes={"reads": "as in B10, plus endNames: names of Connector::connectorEnd in order",
                  "through": "a path: each element is read as a member visible in the previous one"})
for read in READS:
    for kind in KIND_COL:
        for depth in DEPTH_COL:
            for loc in LOC_COL:
                src, tgt = ENDS[depth]
                expect = {"endCount": 2, "endNames": ["supplier", "consumer"], "endReferences": [src, tgt],
                          "sourceFeature": src, "targetFeature": [tgt], "relatedFeature": [src, tgt]}[read]
                el = V + ("c" if kind == "connection" else "i") + str(depth)
                m.add({READ_COL[read], KIND_COL[kind], DEPTH_COL[depth], LOC_COL[loc]}, read, el, expect, THROUGH[loc])
m.write("gen_b12.py")
