#!/usr/bin/env python3
"""Matrix C20 - kinds of action.

Full cross product: reads x action kind (send via, send to, accept via, assign, perform,
if, while, for) x location (in an action def body, nested in an action usage owned by a
part def, read through a typing usage of that part def).

Reads (an argument is compared as the referenced features of its expression, each in
chain form, as in C10; null when the action has no such argument):
  kind              the action's metaclass (SendActionUsage, AcceptActionUsage, ...)
  payloadArgument   SendActionUsage/AcceptActionUsage::payloadArgument
  senderArgument    SendActionUsage::senderArgument (`via` of a send)
  receiverArgument  SendActionUsage::receiverArgument (`to` of a send) or
                    AcceptActionUsage::receiverArgument (`via` of an accept)
  assignedFeature   AssignmentActionUsage::referent, in chain form
State entry actions are left to C30.
"""
from genlib import Matrix

READS = ["kind", "payloadArgument", "senderArgument", "receiverArgument", "assignedFeature"]
READ_COL = {"kind": "can get kind", "payloadArgument": "can get payload", "senderArgument": "can get sender",
            "receiverArgument": "can get receiver", "assignedFeature": "can get assigned feature"}
KINDS = {  # kind -> (action name, metaclass, payload, sender, receiver, assigned); X = the owner of the features
    "sendVia": ("sendVia", "SendActionUsage", "alarm", "alarmPort", None, None),
    "sendTo": ("sendTo", "SendActionUsage", "alarm", None, "display", None),
    "accept": ("acceptVia", "AcceptActionUsage", None, None, "alarmPort", None),
    "assign": ("assignCount", "AssignmentActionUsage", None, None, None, "count"),
    "perform": ("performNotify", "PerformActionUsage", None, None, None, None),
    "if": ("ifAct", "IfActionUsage", None, None, None, None),
    "while": ("whileAct", "WhileLoopActionUsage", None, None, None, None),
    "for": ("forAct", "ForLoopActionUsage", None, None, None, None),
}
KIND_COL = {k: k.replace("sendVia", "send via").replace("sendTo", "send to").replace("accept", "accept via")
            for k in KINDS}
LOC_COL = {"ADEF": "in action def", "AUSE": "nested in action usage in part def", "L3": "read through typing usage"}
LOC = {  # location -> (owner of the action, owner of the referenced features, through)
    "ADEF": ("C20::Supervise", "C20::Supervise", None),
    "AUSE": ("C20::Monitor::supervise", "C20::Monitor", None),
    "L3": ("C20::Monitor::supervise", "C20::Monitor", ["C20::monitor", "C20::Monitor::supervise"]),
}

m = Matrix("C20", "kinds of action", "models/C20.sysml",
           list(READ_COL.values()) + list(KIND_COL.values()) + list(LOC_COL.values()),
           description="Actions of each kind, read for their metaclass and their arguments.",
           notes={"reads": __doc__.split("Reads (")[1].strip(),
                  "through": "a path: each element is read as a member visible in the previous one"})
for read in READS:
    for kind, (name, metaclass, payload, sender, receiver, assigned) in KINDS.items():
        for loc in LOC_COL:
            action_owner, feature_owner, through = LOC[loc]
            ref = lambda f: [[f"{feature_owner}::{f}"]] if f else None
            expect = {"kind": metaclass, "payloadArgument": ref(payload), "senderArgument": ref(sender),
                      "receiverArgument": ref(receiver),
                      "assignedFeature": [f"{feature_owner}::{assigned}"] if assigned else None}[read]
            m.add({READ_COL[read], KIND_COL[kind], LOC_COL[loc]}, read, f"{action_owner}::{name}", expect, through)
m.write("gen_c20.py")
