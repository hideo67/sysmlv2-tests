#!/usr/bin/env python3
"""Matrix A03 - definition modifiers.

Full cross product: reads x modifier (none, `abstract`, `variation` with two variants,
`individual`) x definition kind (part, item, occurrence, action: definitions whose grammar
rule takes OccurrenceDefinitionPrefix, so they accept every modifier; a port def does not
take `individual`) x location (owned by a package, nested in a part def).

Reads:
  isAbstract    Type::isAbstract; a variation definition is abstract (SysML: a variation
                must be abstract), so `variation` gives true as well
  isVariation   Definition::isVariation
  isIndividual  OccurrenceDefinition::isIndividual
  variants      sorted names of Definition::variant ([] for a definition that is not a variation)
"""
from genlib import Matrix

READS = ["isAbstract", "isVariation", "isIndividual", "variants"]
READ_COL = {"isAbstract": "can tell abstract", "isVariation": "can tell variation",
            "isIndividual": "can tell individual", "variants": "can list variants"}
MOD_COL = {"Plain": "no modifier", "Abs": "abstract", "Var": "variation", "Ind": "individual"}
KIND_COL = {"Part": "part def", "Item": "item def", "Occ": "occurrence def", "Act": "action def"}
LOC_COL = {"DL1": "owned by package", "DL2": "nested in part def"}
OWNER = {"DL1": "A03", "DL2": "A03::Holder"}
EXPECT = {  # modifier -> (isAbstract, isVariation, isIndividual, variants)
    "Plain": (False, False, False, []), "Abs": (True, False, False, []),
    "Var": (True, True, False, ["v1", "v2"]), "Ind": (False, False, True, []),
}

m = Matrix("A03", "definition modifiers", "models/A03.sysml",
           list(READ_COL.values()) + list(MOD_COL.values()) + list(KIND_COL.values()) + list(LOC_COL.values()),
           description="The abstract, variation and individual modifiers on occurrence definitions.",
           notes={"reads": __doc__.split("Reads:")[1].strip()})
for read in READS:
    for mod in MOD_COL:
        for kind in KIND_COL:
            for loc in LOC_COL:
                expect = dict(zip(READS, EXPECT[mod]))[read]
                m.add({READ_COL[read], MOD_COL[mod], KIND_COL[kind], LOC_COL[loc]}, read,
                      f"{OWNER[loc]}::{kind}{mod}", expect)
m.write("gen_a03.py")
