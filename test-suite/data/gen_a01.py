#!/usr/bin/env python3
"""Matrix A01 - structural definitions.

Two blocks, each a full cross product:
  1. reads (name, shortName, kind) x definition kind (10) x location
       (DL1 owned by a package, DL2 nested in a part def, DL3 in a nested package)
  2. reads (name, kind, isAbstract) x the standard-library definition of each kind
       (DL5); the library has no SysML occurrence def, so that kind has no case here

Reads:
  name        Element::name
  shortName   Element::shortName
  kind        the metaclass (PartDefinition, ...)
  isAbstract  Type::isAbstract
Reads through an import or alias (DL4) are left to A60; isVariation and isIndividual to A03.
"""
from genlib import Matrix

KINDS = {  # kind -> (name, short name, metaclass, library definition, library abstract)
    "part": ("PartD", "PD", "PartDefinition", "Parts::Part", True),
    "item": ("ItemD", "ID", "ItemDefinition", "Items::Item", True),
    "attribute": ("AttrD", "AD", "AttributeDefinition", "Quantities::TensorQuantityValue", True),
    "port": ("PortD", "POD", "PortDefinition", "Ports::Port", True),
    "connection": ("ConnD", "CD", "ConnectionDefinition", "Connections::Connection", True),
    "interface": ("IfaceD", "IFD", "InterfaceDefinition", "Interfaces::Interface", True),
    "allocation": ("AllocD", "ALD", "AllocationDefinition", "Allocations::Allocation", False),
    # an enumeration def is a variation, and a variation def is abstract (SysML), so VerdictKind is abstract
    "enum": ("EnumD", "ED", "EnumerationDefinition", "VerificationCases::VerdictKind", True),
    "occurrence": ("OccD", "OD", "OccurrenceDefinition", None, None),
    "metadata": ("MetaD", "MD", "MetadataDefinition", "Metadata::MetadataItem", True),
}
READ_COL = {"name": "can read name", "shortName": "can read short name", "kind": "can get kind",
            "isAbstract": "can tell abstract"}
KIND_COL = {k: f"{k} def" for k in KINDS}
LOC_COL = {"DL1": "owned by package", "DL2": "nested in part def", "DL3": "in nested package",
           "DL5": "standard library"}
OWNER = {"DL1": "A01", "DL2": "A01::Holder", "DL3": "A01::Inner"}

m = Matrix("A01", "structural definitions", "models/A01.sysml",
           list(READ_COL.values()) + list(KIND_COL.values()) + list(LOC_COL.values()),
           description="Definitions of each structural kind, in the model and in the standard library.",
           notes={"reads": __doc__.split("Reads:")[1].strip()})
for read in ["name", "shortName", "kind"]:
    for kind, (name, short, metaclass, _, _) in KINDS.items():
        for loc in ["DL1", "DL2", "DL3"]:
            expect = {"name": name, "shortName": short, "kind": metaclass}[read]
            m.add({READ_COL[read], KIND_COL[kind], LOC_COL[loc]}, read, f"{OWNER[loc]}::{name}", expect)
for read in ["name", "kind", "isAbstract"]:
    for kind, (_, _, metaclass, lib, abstract) in KINDS.items():
        if lib is None:
            continue
        expect = {"name": lib.split("::")[-1], "kind": metaclass, "isAbstract": abstract}[read]
        m.add({READ_COL[read], KIND_COL[kind], LOC_COL["DL5"]}, read, lib, expect)
m.write("gen_a01.py")
