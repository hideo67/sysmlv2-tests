#!/usr/bin/env python3
"""Matrix A60 - namespaces: imports, aliases and visibility.

Full cross product: reads x access path (own member, alias, membership import, namespace
import, recursive import `::**`, private import, private member, protected member) x
element kind (a part def, referenced by a usage typed by it; an attribute usage, referenced
by an attribute subsetting it).

Reads:
  resolve          the element the qualified path resolves to, as its declared qualified name:
                   KerML Namespace::resolve of the rest of the path on the matrix's root package
                   (A60.resolve("Lib::Pump")), which respects visibility after the first segment;
                   null when the path is not visible from outside (a private import, a private
                   member, a protected member). OpenSysML's Symbol API has one lookup,
                   get(qualified name), which is given the whole path.
  referenceTarget  the element a reference written through the path resolves to: the type of
                   the typed usage, or the subsetted feature of the subsetting attribute. The
                   references to private and protected paths are written where those are visible.
"""
from genlib import Matrix

READ_COL = {"resolve": "can resolve qualified name", "referenceTarget": "reference resolves"}
PATH_COL = {"own": "own member", "alias": "alias", "memImport": "membership import",
            "nsImport": "namespace import", "recImport": "recursive import", "privImport": "private import",
            "privMember": "private member", "protected": "protected member"}
KIND_COL = {"def": "part def (typing)", "attr": "attribute (subsetting)"}
L = "A60::Lib::"
PATHS = {  # path -> {kind: (qualified path, declared target, visible from outside, referencing element)}
    "own": {"def": ("A60::Lib::Pump", L + "Pump", True, "A60::Client::pOwn"),
            "attr": ("A60::Lib::rate", L + "rate", True, "A60::Client::aOwn")},
    "alias": {"def": ("A60::Lib::PumpAlias", L + "Pump", True, "A60::Client::pAlias"),
              "attr": ("A60::Lib::rateAlias", L + "rate", True, "A60::Client::aAlias")},
    "memImport": {"def": ("A60::Facade::Pump", L + "Pump", True, "A60::Client::pMem"),
                  "attr": ("A60::Facade::rate", L + "rate", True, "A60::Client::aMem")},
    "nsImport": {"def": ("A60::FacadeAll::Pump", L + "Pump", True, "A60::Client::pNs"),
                 "attr": ("A60::FacadeAll::rate", L + "rate", True, "A60::Client::aNs")},
    "recImport": {"def": ("A60::FacadeDeep::Valve", L + "Sub::Valve", True, "A60::Client::pRec"),
                  "attr": ("A60::FacadeDeep::volume", L + "Sub::volume", True, "A60::Client::aRec")},
    "privImport": {"def": ("A60::Hidden::Pump", L + "Pump", False, "A60::Hidden::pUse"),
                   "attr": ("A60::Hidden::rate", L + "rate", False, "A60::Hidden::aUse")},
    "privMember": {"def": ("A60::Lib::SecretDef", L + "SecretDef", False, "A60::Lib::pSecret"),
                   "attr": ("A60::Lib::secretRate", L + "secretRate", False, "A60::Lib::aSecret")},
    "protected": {"def": ("A60::Base::ProtDef", "A60::Base::ProtDef", False, "A60::Derived::pUse"),
                  "attr": ("A60::Base::protRate", "A60::Base::protRate", False, "A60::Derived::aUse")},
}

m = Matrix("A60", "namespaces: imports, aliases and visibility", "models/A60.sysml",
           list(READ_COL.values()) + list(PATH_COL.values()) + list(KIND_COL.values()),
           description="Elements reached through aliases, imports and visibility rules.",
           notes={"reads": __doc__.split("Reads:")[1].strip(),
                  "via": "referenceTarget: `type` reads the first type of the element, `subsetting` "
                         "the subsetted feature of its explicit owned subsetting"})
for read in READ_COL:
    for path in PATH_COL:
        for kind in KIND_COL:
            qpath, target, visible, ref = PATHS[path][kind]
            if read == "resolve":
                m.add({READ_COL[read], PATH_COL[path], KIND_COL[kind]}, "resolve", qpath, target if visible else None)
            else:
                m.add({READ_COL[read], PATH_COL[path], KIND_COL[kind]}, "referenceTarget", ref, target,
                      via="type" if kind == "def" else "subsetting")
m.write("gen_a60.py")
