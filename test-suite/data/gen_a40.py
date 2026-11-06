#!/usr/bin/env python3
"""Matrix A40 - specialization relations of usages.

Full cross product: reads x relation (feature typing, subsetting, reference subsetting,
typing and subsetting, redefinition) x location (L2 owned by a part def, L3 read through a
typing usage, L4 read through a usage of a specialized def).

Reads (sorted lists; implied relationships, such as the subsetting of Parts::parts that
every part usage gets, are left out):
  specializations    [metaclass, general] of each explicit owned Specialization
                     (FeatureTyping, Subsetting, ReferenceSubsetting, Redefinition)
  subsettedFeatures  subsettedFeature of each explicit owned Subsetting (redefinitions and
                     reference subsettings are subsettings too)
  types              Feature::type
"""
from genlib import Matrix

READS = ["specializations", "subsettedFeatures", "types"]
READ_COL = {"specializations": "can get specializations", "subsettedFeatures": "can get subsetted features",
            "types": "can get types"}
REL_COL = {"typing": "feature typing", "subset": "subsetting", "ref": "reference subsetting",
           "both": "typing and subsetting", "redef": "redefinition"}
LOC_COL = {"L2": "appears in part def", "L3": "read through typing usage",
           "L4": "read through usage of specialized def"}
Q = "A40::Owner::q"
REL = {  # relation -> (element, specializations, subsetted, types)
    "typing": ("A40::Owner::pTyped", [["FeatureTyping", "A40::T"]], [], ["A40::T"]),
    "subset": ("A40::Owner::pSub", [["Subsetting", Q]], [Q], ["A40::T"]),
    "ref": ("A40::Owner::pRef", [["ReferenceSubsetting", Q]], [Q], ["A40::T"]),
    "both": ("A40::Owner::pBoth", [["FeatureTyping", "A40::V"], ["Subsetting", Q]], [Q], ["A40::T", "A40::V"]),
    "redef": ("A40::SubOwner::q", [["Redefinition", Q]], [Q], ["A40::T"]),
}
THROUGH = {  # the redefinition lives in SubOwner, so its usages are one level further down
    "L2": {"other": None, "redef": None},
    "L3": {"other": ["A40::owner"], "redef": ["A40::subOwner"]},
    "L4": {"other": ["A40::subOwner"], "redef": ["A40::subSub"]},
}

m = Matrix("A40", "specialization relations of usages", "models/A40.sysml",
           list(READ_COL.values()) + list(REL_COL.values()) + list(LOC_COL.values()),
           description="Usages related to a type or another feature by each kind of specialization.",
           notes={"reads": __doc__.split("Reads (")[1].strip()})
for read in READS:
    for rel, (el, specs, subsetted, types) in REL.items():
        for loc in LOC_COL:
            expect = {"specializations": specs, "subsettedFeatures": subsetted, "types": types}[read]
            through = THROUGH[loc]["redef" if rel == "redef" else "other"]
            m.add({READ_COL[read], REL_COL[rel], LOC_COL[loc]}, read, el, expect, through)
m.write("gen_a40.py")
