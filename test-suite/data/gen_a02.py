#!/usr/bin/env python3
"""Matrix A02 - definition specialization.

Full cross product: reads x definition (Base: no explicit general; Mid :> Base; Leaf :> Mid
with a redefinition; Multi :> Base, Other; FromAbs :> abstract AbsBase) x location
(DL1 owned by the package, DL3 the same set in a nested package).

Reads (sorted lists):
  directGenerals         superclassifiers of the explicit (not implied) owned subclassifications
  allSupertypes          Type::allSupertypes() = OrderedSet{self}->closure(supertypes(false)): every
                         direct and indirect supertype, implied ones included, so the library types
                         Parts::Part ... Base::Anything. An OCL closure does not contain its source,
                         so the type itself is not included.
  ownedFeatureNames      names of Type::ownedFeature
  inheritedFeatureNames  names of Type::inheritedFeature, members inherited from the standard
                         library included (DISCUSSIONS.md, Step 3 decision)
  redefinitions          [redefining feature, redefined feature] of the owned features' redefinitions
Cases marked `libraryDependent` expect members of the standard library; their library part
was taken from the Pilot Implementation (library 0.64.0) and checked against the library source.
"""
from genlib import Matrix

READS = ["directGenerals", "allSupertypes", "ownedFeatureNames", "inheritedFeatureNames", "redefinitions"]
READ_COL = {"directGenerals": "can get direct generals", "allSupertypes": "can get all supertypes",
            "ownedFeatureNames": "can list owned features", "inheritedFeatureNames": "can list inherited features",
            "redefinitions": "can get redefinitions"}
DEF_COL = {"Base": "no explicit general", "Mid": "single general", "Leaf": "two levels and redefinition",
           "Multi": "multiple generals", "FromAbs": "abstract general"}
LOC_COL = {"DL1": "owned by package", "DL3": "in nested package"}
PKG = {"DL1": "A02", "DL3": "A02::Far"}

# Supertypes of every part def through the implied Parts::Part (Parts.sysml, Items.sysml,
# Objects.kerml, Occurrences.kerml, Base.kerml).
LIB_SUPERTYPES = ["Base::Anything", "Items::Item", "Objects::Object", "Occurrences::Occurrence", "Parts::Part"]
# Features a part def inherits from Parts::Part and its supertypes: the Pilot's answer
# (library 0.64.0), checked so that every name is declared in Parts.sysml, Items.sysml,
# Objects.kerml, Occurrences.kerml or Base.kerml. "" stands for an unnamed feature.
LIB_PART_FEATURES = [
    "boundingShapes", "checkedConstraints", "differencesOf", "dispatchScope", "done",
    "enactedPerformances", "envelopingShapes", "exhibitedStates", "immediatePredecessors",
    "immediateSuccessors", "incomingTransferSort", "incomingTransfers", "incomingTransfersToSelf",
    "innerSpaceDimension", "intersectionsOf", "involvingPerformances", "isClosed", "isDispatch",
    "isRunToCompletion", "isSolid", "justOutsideOfOccurrences", "localClock", "matingOccurrences",
    "middleTimeSlice", "outerSpaceDimension", "outgoingTransfers", "outgoingTransfersFromSelf",
    "outsideOfOccurrences", "ownedActions", "ownedPerformances", "ownedPorts", "ownedStates",
    "performedActions", "portionOf", "portionOfLife", "portions", "predecessors",
    "runToCompletionScope", "sameLifeOccurrences", "self", "shape", "snapshotOf", "snapshots",
    "spaceBoundaryOf", "spaceEnclosedOccurrences", "spaceInterior", "spaceInteriorOf",
    "spaceShotOf", "spaceShots", "spaceSliceOf", "spaceSlices", "spaceTimeCoincidentOccurrences",
    "spaceTimeEnclosedOccurrences", "spaceTimeEnclosedPoints", "start", "structuredSpaceBoundary",
    "subitems", "subobjects", "suboccurrences", "subparts", "successors", "superoccurrence",
    "surroundedByOccurrences", "this", "timeCoincidentOccurrences", "timeEnclosedOccurrences",
    "timeSliceOf", "timeSlices", "unionsOf", "voids", "withoutOccurrences",
] + [""] * 18

GENERALS = {"Base": [], "Mid": ["Base"], "Leaf": ["Mid"], "Multi": ["Base", "Other"], "FromAbs": ["AbsBase"]}
CLOSURE = {"Base": [], "Mid": ["Base"], "Leaf": ["Mid", "Base"],
           "Multi": ["Base", "Other"], "FromAbs": ["AbsBase"]}
OWNED = {"Base": ["a", "x"], "Mid": ["b"], "Leaf": ["c", "x"], "Multi": ["m"], "FromAbs": ["f"]}
INHERITED = {"Base": [], "Mid": ["a", "x"], "Leaf": ["a", "b"],   # Leaf's own x redefines Base::x
             "Multi": ["a", "o", "x"], "FromAbs": ["ab"]}

m = Matrix("A02", "definition specialization", "models/A02.sysml",
           list(READ_COL.values()) + list(DEF_COL.values()) + list(LOC_COL.values()),
           description="Generals, supertypes, and own and inherited features of specializing definitions.",
           notes={"reads": __doc__.split("Reads (sorted lists):")[1].strip()})
for read in READS:
    for d in DEF_COL:
        for loc in LOC_COL:
            p = PKG[loc]
            q = lambda names: sorted(f"{p}::{n}" for n in names)
            extra = {}
            if read == "directGenerals":
                expect = q(GENERALS[d])
            elif read == "allSupertypes":
                expect = sorted(q(CLOSURE[d]) + LIB_SUPERTYPES)
                # Whether an OCL closure contains its source is read both ways in practice
                # (Eclipse OCL, under the Pilot, leaves it out); the list with the type itself
                # is accepted too.
                extra["accept"] = [sorted(expect + [f"{p}::{d}"])]
            elif read == "ownedFeatureNames":
                expect = sorted(OWNED[d])
            elif read == "inheritedFeatureNames":
                expect = sorted(INHERITED[d] + LIB_PART_FEATURES) if LIB_PART_FEATURES is not None else None
                extra["libraryDependent"] = True
            else:
                expect = [[f"{p}::Leaf::x", f"{p}::Base::x"]] if d == "Leaf" else []
            m.add({READ_COL[read], DEF_COL[d], LOC_COL[loc]}, read, f"{p}::{d}", expect, **extra)
m.write("gen_a02.py")
