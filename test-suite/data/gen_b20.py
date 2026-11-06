#!/usr/bin/env python3
"""Matrix B20 - flows.

Two blocks, each a full cross product:
  1. reads x flow kind (`flow`, `succession flow`) x end depth (1: `tank.fuelOut`,
     2: `m.tank.fuelOut`; a flow end must name a participant with dot notation, so there is no
     depth 0) x location (L2 owned by a part def, L3 through a typing usage, L6 through a
     nested usage chain)
  2. reads x a `message of Sig from tank to engine` x location

A flow end is not a plain reference (KerML FlowEnd): `from tank.fuelOut` gives an end whose
ReferenceSubsetting references `tank` (the chain before the last name, if any) and which owns a
flow feature redefining `fuelOut`. A message's `from tank to engine` are not connector ends: the
grammar makes each a ParameterMembership (MessageEventMember) owning an EventOccurrenceUsage that
references `tank`/`engine`. So the message's ends reference nothing and own no flow feature.
Reads:
  kind           the metaclass (FlowUsage, SuccessionFlowUsage)
  payloadTypes   sorted qualified names of Flow::payloadType
  endReferences  for each connector end, its ReferenceSubsetting's referencedFeature in chain
                 form (B10)
  sourceOutput   the feature redefined by Flow::sourceOutputFeature (what the flow draws from);
                 null when the flow has none (a message)
  targetInput    the feature redefined by Flow::targetInputFeature
"""
from genlib import Matrix

READS = ["kind", "payloadTypes", "endReferences", "sourceOutput", "targetInput"]
READ_COL = {"kind": "can get kind", "payloadTypes": "can get payload type", "endReferences": "can get end references",
            "sourceOutput": "can get source output", "targetInput": "can get target input"}
KIND_COL = {"flow": "flow", "succ": "succession flow", "msg": "message"}
DEPTH_COL = {1: "end depth 1", 2: "end depth 2"}
LOC_COL = {"L2": "appears in part def", "L3": "read through typing usage", "L6": "read through nested usage chain"}
V = "B20::Vehicle::"
THROUGH = {"L2": None, "L3": ["B20::vehicle"], "L6": ["B20::fleet", "B20::Fleet::v"]}
ENDS = {1: [[V + "tank"], [V + "engine"]],
        2: [[V + "m", "B20::Module::tank"], [V + "n", "B20::Module::engine"]]}
OUT_IN = {1: ("B20::Tank::fuelOut", "B20::Engine::fuelIn"),
          2: ("B20::Tank::fuelOut", "B20::Engine::fuelIn")}

m = Matrix("B20", "flows", "models/B20.sysml",
           list(READ_COL.values()) + list(KIND_COL.values()) + list(DEPTH_COL.values()) + list(LOC_COL.values()),
           description="Flows, succession flows and messages, read for their payload and ends.",
           notes={"reads": __doc__.split("Reads:")[1].strip(),
                  "through": "a path: each element is read as a member visible in the previous one"})
for read in READS:
    for kind, metaclass, prefix in [("flow", "FlowUsage", "f"), ("succ", "SuccessionFlowUsage", "s")]:
        for depth in DEPTH_COL:
            for loc in LOC_COL:
                out, inp = OUT_IN[depth]
                expect = {"kind": metaclass, "payloadTypes": ["B20::Fuel"],
                          "endReferences": ENDS[depth],
                          "sourceOutput": out, "targetInput": inp}[read]
                m.add({READ_COL[read], KIND_COL[kind], DEPTH_COL[depth], LOC_COL[loc]}, read,
                      f"{V}{prefix}{depth}", expect, THROUGH[loc])
for read in READS:
    for loc in LOC_COL:
        expect = {"kind": "FlowUsage", "payloadTypes": ["B20::Sig"],
                  "endReferences": [None, None], "sourceOutput": None, "targetInput": None}[read]
        m.add({READ_COL[read], KIND_COL["msg"], LOC_COL[loc]}, read, V + "msg", expect, THROUGH[loc])
m.write("gen_b20.py")
