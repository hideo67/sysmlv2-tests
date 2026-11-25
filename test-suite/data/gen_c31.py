#!/usr/bin/env python3
"""Matrix C31 - perform and exhibit targets.

What a perform action or an exhibited state performs or exhibits. A full cross product:
reads x variant x location (L2 in the part def, L3 through a typing usage of it, L4 through a
usage of a def that specializes it).

Variants (all PerformActionUsages; an ExhibitStateUsage is one too):
  performRef   `perform shared;` in the part def: by reference, to a package-level action
  performDecl  `perform action own : Run;`: declared, so it performs itself
  exhibitRef   `exhibit sharedModes;`: by reference, to a package-level state
  exhibitDecl  `exhibit state modes { ... }`: declared, so it exhibits itself
  stateRef     `perform real;` in a state of `modes`: by reference, to the part def's action
  stateDo      `do action work;` in a state: declared (a PerformActionUsage by the grammar's
               PerformActionUsageDeclaration), so it performs itself
  entryRef     `entry real;` in a state: by reference, to the part def's action
A perform or exhibit by reference has no declared name; it is located by its effective name,
the referenced feature's (`...::normal::real`).

Reads:
  performedAction  PerformActionUsage::performedAction (qualified name): the referenced
                   feature of its ownedReferenceSubsetting, or else the usage itself
  exhibitedState   ExhibitStateUsage::exhibitedState (qualified name), derived the same way;
                   null for a usage that is not an ExhibitStateUsage
"""
from genlib import Matrix

READ_COL = {"performedAction": "can get performed action", "exhibitedState": "can get exhibited state"}
VAR_COL = {"performRef": "perform by reference", "performDecl": "perform, declared",
           "exhibitRef": "exhibit by reference", "exhibitDecl": "exhibit, declared",
           "stateRef": "perform by reference in a state", "stateDo": "do action in a state",
           "entryRef": "entry action by reference"}
LOC_COL = {"L2": "appears in part def", "L3": "read through typing usage",
           "L4": "read through usage of specialized def"}
M = "C31::Machine::"
# variant -> (element, the states it is nested in, performed action, is an exhibit)
VARIANTS = {
    "performRef": (M + "shared", [], "C31::shared", False),
    "performDecl": (M + "own", [], M + "own", False),
    "exhibitRef": (M + "sharedModes", [], "C31::sharedModes", True),
    "exhibitDecl": (M + "modes", [], M + "modes", True),
    "stateRef": (M + "modes::normal::real", [M + "modes", M + "modes::normal"], M + "real", False),
    "stateDo": (M + "modes::normal::work", [M + "modes", M + "modes::normal"], M + "modes::normal::work", False),
    "entryRef": (M + "modes::idle::real", [M + "modes", M + "modes::idle"], M + "real", False),
}
USAGE = {"L2": None, "L3": "C31::machine", "L4": "C31::subMachine"}

m = Matrix("C31", "perform and exhibit targets", "models/C31.sysml",
           list(READ_COL.values()) + list(VAR_COL.values()) + list(LOC_COL.values()),
           description="What a perform action or an exhibited state performs or exhibits.",
           notes={"reads": __doc__.split("Reads:")[1].strip(),
                  "through": "a path: each element is read as a member visible in the previous one"})
for read in READ_COL:
    for var, (el, states, performed, exhibit) in VARIANTS.items():
        for loc, usage in USAGE.items():
            through = ([usage] + states) if usage else None
            expect = performed if read == "performedAction" or exhibit else None
            m.add({READ_COL[read], VAR_COL[var], LOC_COL[loc]}, read, el, expect, through)
m.write("gen_c31.py")
