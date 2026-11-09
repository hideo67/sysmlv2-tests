#!/usr/bin/env python3
"""Matrix B13 - succession ends and connector ends declared in the body.

Two blocks, each a full cross product:
  1. reads on a succession x form x location (DEF the action/state def itself, L3 through a
     typing usage, L6 through a nested usage chain: plant.<usage>). Forms:
       named       `succession s first a1 then a2;`
       unnamed     `first a1 then a2;`
       shorthand   `first a1; then a2;`
       to node     `first a1; then accept Sig;` (the target is the unnamed accept node)
       from node   `... then accept Sig; then action a3;` (the source is the accept node)
       guarded     `succession g first d if true then a1;` (a TransitionUsage; read: its succession)
       transition  `transition t first s1 accept Sig then s2;` (read: the transition's succession)
  2. reads on a connection or interface usage whose ends are declared in its body
       x kind (connection, interface) x end form (`end :>> e1 ::> d1;` redefining the def's
       ends, `end f1 ::> d1;` own ends) x location (L2 owned by part def, L3, L6)

Reads are those of B10: endCount, endReferences, sourceFeature, targetFeature, relatedFeature
(see its notes). An unnamed referenced feature (the accept node) is written as [null].
Expected values are those of the SysML v2 Pilot Implementation.
"""
from genlib import Matrix

READS = ["endCount", "endReferences", "sourceFeature", "targetFeature", "relatedFeature"]
READ_COL = {"endCount": "can count ends", "endReferences": "can get end references",
            "sourceFeature": "can get sourceFeature", "targetFeature": "can get targetFeature",
            "relatedFeature": "can get relatedFeature"}
FORM_COL = {"named": "named succession", "unnamed": "unnamed succession", "shorthand": "then shorthand",
            "toNode": "target is an unnamed node", "fromNode": "source is an unnamed node",
            "guarded": "guarded succession", "transition": "state transition"}
KIND_COL = {"connection": "body ends of connection", "interface": "body ends of interface"}
END_COL = {"redefined": "ends redefine the def's ends", "own": "own ends"}
LOC_COL = {"DEF": "appears in action or state def", "L2": "appears in part def",
           "L3": "read through typing usage", "L6": "read through nested usage chain"}

SUCC = "SuccessionAsUsage"
# form: (def, usage name, element in the def, unnamed selector, source, target)
FORMS = {
    "named": ("Named", "named", "s", None, "a1", "a2"),
    "unnamed": ("Unnamed", "unnamed", None, 0, "a1", "a2"),
    "shorthand": ("Shorthand", "shorthand", None, 0, "a1", "a2"),
    "toNode": ("NodeEnds", "nodeEnds", None, 0, "a1", None),
    "fromNode": ("NodeEnds", "nodeEnds", None, 1, None, "a3"),
    "guarded": ("Guarded", "guarded", "g", 0, "d", "a1"),
    "transition": ("Machine", "machine", "t", 0, "s1", "s2"),
}


def expect_of(read, src, tgt):
    return {"endCount": 2, "endReferences": [src, tgt], "sourceFeature": src,
            "targetFeature": [tgt], "relatedFeature": [src, tgt]}[read]


m = Matrix("B13", "succession ends and body-declared connector ends", "models/B13.sysml",
           list(READ_COL.values()) + list(FORM_COL.values()) + list(KIND_COL.values())
           + list(END_COL.values()) + list(LOC_COL.values()),
           description="Successions in their written forms, and connection/interface usages whose ends "
                       "are declared in their body, read for their ends.",
           notes={"reads": "as in B10; an unnamed referenced feature (an action node) is written as [null]",
                  "unnamed": "locates an unnamed element: {metaclass, index} among the unnamed members "
                             "of that metaclass declared in `element`, in declaration order",
                  "through": "a path: each element is read as a member visible in the previous one"})
for read in READS:
    for form, (d, use, el, idx, s, t) in FORMS.items():
        for loc in ["DEF", "L3", "L6"]:
            q = f"B13::{d}::"
            src = [q + s] if s else [None]
            tgt = [q + t] if t else [None]
            through = {"DEF": [], "L3": [f"B13::{use}"], "L6": ["B13::plant", f"B13::Plant::{use}"]}[loc]
            marks = {READ_COL[read], FORM_COL[form], LOC_COL[loc]}
            expect = expect_of(read, src, tgt)
            if idx is None:                     # a named succession, read by its name
                m.add(marks, read, q + el, expect, through or None)
            elif el is None:                    # an unnamed succession of the def
                m.add(marks, read, f"B13::{d}", expect, through or None,
                      unnamed={"metaclass": SUCC, "index": idx})
            else:                               # the unnamed succession of a named transition
                m.add(marks, read, q + el, expect, (through + [q + el]) if through else None,
                      unnamed={"metaclass": SUCC, "index": idx})
CONN = {("connection", "redefined"): ("k1", "d1", "d2"), ("connection", "own"): ("k2", "d1", "d2"),
        ("interface", "redefined"): ("j1", "p1", "p2"), ("interface", "own"): ("j2", "p1", "p2")}
for read in READS:
    for (kind, ends), (el, s, t) in CONN.items():
        for loc in ["L2", "L3", "L6"]:
            through = {"L2": None, "L3": ["B13::sys"], "L6": ["B13::plant", "B13::Plant::sys"]}[loc]
            m.add({READ_COL[read], KIND_COL[kind], END_COL[ends], LOC_COL[loc]}, read, "B13::Sys::" + el,
                  expect_of(read, ["B13::Sys::" + s], ["B13::Sys::" + t]), through)
m.write("gen_b13.py")
