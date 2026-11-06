#!/usr/bin/env python3
"""Matrix A10 - part usages: the full cross product of
(what is read) x (where the usage appears) x (kind of usage)."""
from genlib import Matrix

READS = ["name", "type", "isComposite", "isReference"]
READ_COL = {"name": "can read name", "type": "can get type",
            "isComposite": "can tell composite", "isReference": "can tell reference"}
LOC_COL = {"package": "appears in package", "part def": "appears in part def",
           "inherited": "read through typing usage",
           "specialized": "read through usage of specialized def"}
KINDS = ["owned", "ref"]
KIND_COL = {"owned": "owned part", "ref": "ref part"}
# Locations are generated in groups; a group added later is appended after the
# existing ones so that published IDs stay stable.
GROUPS = [["package", "part def", "inherited"], ["specialized"]]

# (loc, kind) -> (element, through, name, type, isComposite)
ELEM = {
    ("package", "owned"):   ("A10::car", None, "car", "A10::Car", False),  # no owning type, so not composite (Pilot, sysml-toolkit agree)
    ("package", "ref"):     ("A10::owner", None, "owner", "A10::Person", False),
    ("part def", "owned"):  ("A10::Car::engine", None, "engine", "A10::Engine", True),
    ("part def", "ref"):    ("A10::Car::driver", None, "driver", "A10::Person", False),
    ("inherited", "owned"): ("A10::Car::engine", "A10::car", "engine", "A10::Engine", True),
    ("inherited", "ref"):   ("A10::Car::driver", "A10::car", "driver", "A10::Person", False),
    # Car's members read through a usage typed by SportsCar :> Car
    ("specialized", "owned"): ("A10::Car::engine", "A10::sportsCar", "engine", "A10::Engine", True),
    ("specialized", "ref"):   ("A10::Car::driver", "A10::sportsCar", "driver", "A10::Person", False),
}
# unnamed parts: (loc) -> (owner of the unnamed part, through)
UNNAMED = {"package": ("A10", None), "part def": ("A10::Car", None), "inherited": ("A10::Car", "A10::car"),
           "specialized": ("A10::Car", "A10::sportsCar")}

m = Matrix("A10", "part usages", "models/A10.sysml",
           [READ_COL[r] for r in READS] + ["can list unnamed"] + list(LOC_COL.values()) + list(KIND_COL.values()),
           description="Full cross product of what is read, where the usage appears, and the kind of usage.",
           notes={
               "through": "the member is read as seen from this usage (an inherited member of its type, or of a general type of its type), not from its declaring element",
               "unnamedPartCount": "number of unnamed part usages declared in `element` that are visible (through `through` when given)"})
for group in GROUPS:
    for read in READS:
        for loc in group:
            for kind in KINDS:
                element, through, name, typ, comp = ELEM[(loc, kind)]
                expect = {"name": name, "type": typ, "isComposite": comp, "isReference": not comp}[read]
                m.add({READ_COL[read], LOC_COL[loc], KIND_COL[kind]}, read, element, expect, through)
    for loc in group:
        owner, through = UNNAMED[loc]
        m.add({"can list unnamed", LOC_COL[loc], KIND_COL["owned"]}, "unnamedPartCount", owner, 1, through)
m.write("gen_a10.py")
