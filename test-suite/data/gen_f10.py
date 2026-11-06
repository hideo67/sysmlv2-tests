#!/usr/bin/env python3
"""Matrix F10 - runtime instances.

Full cross product: reads x path depth (1: `tank`, 2: `powertrain.tank` whose capacity is
redefined, 3: `drive.powertrain.tank`) x root (the usage `vehicle`, the part def `Vehicle`).

The root is instantiated with the MDK's instantiation API, and `path` is walked from the root
object through feature values (`a.b.c`). An MDK without an instantiation API is unsupported.
Reads:
  instanceType   the type of the object at `path` (F10::Tank; the usage it was built from,
                 such as F10::Vehicle::tank, is accepted too)
  instanceValue  the value of `capacity` of the object at `path`
  instanceCount  the number of objects `path`.valves holds (declared [2])
  endIdentity    whether the object the connector end `path` holds is the same object as the
                 one at `path2` (the port it references)
  ownerPath      the usage path, from the root, of the object the connector end `path` holds
                 (OpenSysML issue #1959)
"""
from genlib import Matrix

READ_COL = {"instanceType": "can get object type", "instanceValue": "can get object value",
            "instanceCount": "can count objects", "endIdentity": "connector end is same object",
            "ownerPath": "can get usage path"}
DEPTH_COL = {1: "path depth 1", 2: "path depth 2", 3: "path depth 3"}
ROOT_COL = {"usage": "root usage", "def": "root part def"}
ROOT = {"usage": "F10::vehicle", "def": "F10::Vehicle"}
PATH = {1: "tank", 2: "powertrain.tank", 3: "drive.powertrain.tank"}
DECLARED = {1: "F10::Vehicle::tank", 2: "F10::Vehicle::powertrain::tank", 3: "F10::Powertrain::tank"}
CAPACITY = {1: 50.0, 2: 60.0, 3: 50.0}

m = Matrix("F10", "runtime instances", "models/F10.sysml",
           list(READ_COL.values()) + list(DEPTH_COL.values()) + list(ROOT_COL.values()),
           description="Objects built by instantiating a part, read along usage paths.",
           notes={"reads": __doc__.split("Reads:")[1].strip(),
                  "path": "feature names walked from the root object, joined by dots"})
for read in READ_COL:
    for d in DEPTH_COL:
        for root in ROOT_COL:
            p, extra = PATH[d], {}
            if read == "instanceType":
                expect, extra["accept"] = "F10::Tank", [DECLARED[d]]
            elif read == "instanceValue":
                expect, p = CAPACITY[d], p + ".capacity"
            elif read == "instanceCount":
                expect, p = 2, p + ".valves"
            elif read == "endIdentity":
                expect, p, extra["path2"] = True, f"c{d}.src", PATH[d] + ".fuelOut"
            else:
                expect, p = PATH[d] + ".fuelOut", f"c{d}.src"
            m.add({READ_COL[read], DEPTH_COL[d], ROOT_COL[root]}, read, ROOT[root], expect, path=p, **extra)
m.write("gen_f10.py")
