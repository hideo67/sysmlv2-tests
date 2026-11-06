#!/usr/bin/env python3
"""Matrix B10 - connection and interface ends.

Two blocks, each a full cross product:
  1. reads on a connector usage x connector kind (connection, interface)
       x end depth (0: own ports, 1: `x.p`, 2: `m.u1.p`)
       x location (L2 owned by part def, L3 through typing usage, L6 through nested usage chain)
  2. def side: reads on a connection/interface def's end features
       x def kind x location (DL1 the def itself, inherited by a specializing def)

Reads (a referenced feature is written in chain form: the qualified names of its
chainingFeatures, or a one-element list for a feature that is not a chain):
  endCount        number of Connector::connectorEnd (usage) / Type::endFeature (def)
  endReferences   for each connector end, its ReferenceSubsetting's referencedFeature
  sourceFeature   Connector::sourceFeature
  targetFeature   Connector::targetFeature (a list)
  relatedFeature  Connector::relatedFeature (a list): per KerML the ends' referenced
                  features, so for a chained end the chain feature, not its last feature (#1957)
  endNames        names of the def's end features, own and inherited
"""
from genlib import Matrix

READS = ["endCount", "endReferences", "sourceFeature", "targetFeature", "relatedFeature"]
READ_COL = {"endCount": "can count ends", "endReferences": "can get end references",
            "sourceFeature": "can get sourceFeature", "targetFeature": "can get targetFeature",
            "relatedFeature": "can get relatedFeature", "endNames": "can get end names"}
KIND_COL = {"connection": "connection", "interface": "interface"}
DEPTH_COL = {0: "end depth 0", 1: "end depth 1", 2: "end depth 2"}
LOC_COL = {"L2": "appears in part def", "L3": "read through typing usage",
           "L6": "read through nested usage chain", "DL1": "def itself", "DINH": "inherited by specialized def"}

V = "B10::Vehicle::"
ENDS = {0: ([V + "q"], [V + "r"]),
        1: ([V + "x", "B10::Unit::p"], [V + "y", "B10::Unit::p"]),
        2: ([V + "m", "B10::Pair::u1", "B10::Unit::p"], [V + "n", "B10::Pair::u2", "B10::Unit::p"])}
THROUGH = {"L2": None, "L3": ["B10::vehicle"], "L6": ["B10::fleet", "B10::Fleet::v"]}

m = Matrix("B10", "connection and interface ends", "models/B10.sysml",
           list(READ_COL.values()) + list(KIND_COL.values()) + list(DEPTH_COL.values()) + list(LOC_COL.values()),
           description="Connector usages read for their ends, and the end features of connection/interface defs.",
           notes={"reads": __doc__.split("Reads (")[1].strip(),
                  "through": "a path: each element is read as a member visible in the previous one"})
for read in READS:
    for kind in KIND_COL:
        for depth in DEPTH_COL:
            for loc in ["L2", "L3", "L6"]:
                src, tgt = ENDS[depth]
                expect = {"endCount": 2, "endReferences": [src, tgt], "sourceFeature": src,
                          "targetFeature": [tgt], "relatedFeature": [src, tgt]}[read]
                el = V + ("c" if kind == "connection" else "i") + str(depth)
                m.add({READ_COL[read], KIND_COL[kind], DEPTH_COL[depth], LOC_COL[loc]}, read, el, expect, THROUGH[loc])
for read in ["endCount", "endNames"]:
    for kind in KIND_COL:
        for loc in ["DL1", "DINH"]:
            base = "Link" if kind == "connection" else "Iface"
            el = f"B10::{base}" if loc == "DL1" else f"B10::Sub{base}"
            m.add({READ_COL[read], KIND_COL[kind], LOC_COL[loc]}, read, el, 2 if read == "endCount" else ["a", "b"])
m.write("gen_b10.py")
