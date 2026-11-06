#!/usr/bin/env python3
"""Matrix A30 - port usages and conjugation.

Two blocks, each a full cross product:
  1. reads on the port usage (name, type, typeIsConjugated)
       x locations (L2 part def, L3 typing usage, L4 usage of specialized def, L6 nested usage chain)
       x port typing (ordinary `CmdPort`, conjugated `~CmdPort`)
  2. direction of a port def's feature as seen through the port (Type::directionOf)
       x locations (DEF the port def itself, L2, L3, L4, L6)
       x port typing x feature direction as declared (out `cmd`, in `ack`)

Reads:
  name              Element::name of the port usage
  type              qualified name of the first of Feature::type; for ~CmdPort the conjugated
                    port definition `CmdPort::'~CmdPort'` (the unquoted spelling is accepted)
  typeIsConjugated  whether that type is a ConjugatedPortDefinition
  direction         Type::directionOf(feature) of the port usage (or port def) for a feature of
                    the port def: conjugation swaps in and out
"""
from genlib import Matrix

PORT_READS = ["name", "type", "typeIsConjugated"]
READ_COL = {"name": "can read name", "type": "can get type", "typeIsConjugated": "can tell conjugated",
            "direction": "can get direction"}
LOC_COL = {"DEF": "feature of port def", "L2": "appears in part def", "L3": "read through typing usage",
           "L4": "read through usage of specialized def", "L6": "read through nested usage chain"}
PORT_COL = {"normal": "ordinary typing", "conj": "conjugated typing"}
FEAT_COL = {"cmd": "out feature", "ack": "in feature"}

CONJ_DEF = "A30::CmdPort::'~CmdPort'"
PORT = {"normal": ("pOut", "A30::CmdPort", False), "conj": ("pIn", CONJ_DEF, True)}
DECLARED_DIR = {"cmd": "out", "ack": "in"}
FLIP = {"in": "out", "out": "in"}


def port_path(loc, var):
    """(element, through) of the port usage at a location."""
    port = f"A30::Device::{PORT[var][0]}"
    return port, {"L2": None, "L3": ["A30::device"], "L4": ["A30::sub"],
                  "L6": ["A30::rack", "A30::Rack::slot"]}[loc]


m = Matrix("A30", "port usages and conjugation", "models/A30.sysml",
           list(READ_COL.values()) + list(LOC_COL.values()) + list(PORT_COL.values()) + list(FEAT_COL.values()),
           description="Port reads on the port usage, and directions of the port def's features seen through the port.",
           notes={"reads": __doc__.split("Reads:")[1].strip(),
                  "through": "a path: each element is read as a member visible in the previous one"})
for read in PORT_READS:
    for loc in ["L2", "L3", "L4", "L6"]:
        for var in ["normal", "conj"]:
            name, typ, conj = PORT[var]
            el, through = port_path(loc, var)
            expect = {"name": name, "type": typ, "typeIsConjugated": conj}[read]
            extra = {"accept": [typ.replace("'", "")]} if read == "type" and var == "conj" else {}
            m.add({READ_COL[read], LOC_COL[loc], PORT_COL[var]}, read, el, expect, through, **extra)
for loc in ["DEF", "L2", "L3", "L4", "L6"]:
    for var in ["normal", "conj"]:
        for feat in ["cmd", "ack"]:
            if loc == "DEF":
                through = ["A30::CmdPort" if var == "normal" else CONJ_DEF]
            else:
                port, path = port_path(loc, var)
                through = (path or []) + [port]
            d = DECLARED_DIR[feat]
            m.add({READ_COL["direction"], LOC_COL[loc], PORT_COL[var], FEAT_COL[feat]}, "direction",
                  f"A30::CmdPort::{feat}", d if var == "normal" else FLIP[d], through)
m.write("gen_a30.py")
