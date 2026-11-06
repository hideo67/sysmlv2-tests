#!/usr/bin/env python3
"""Matrix C30 - states and transitions.

The cases of the accept-action state use their own model, C30-accept.sysml (package
C30Accept, the same structure), through the case field `model`: an MDK that rejects an accept
action in entry/do/exit then loses only those cases.

Three blocks, each a full cross product with location (DEF in the state def, EXH through an
`exhibit state ex : Ctl` of a part def, L3 through a typing usage of that part def):
  1. entry/do/exit: reads (entryKind, doKind, exitKind) x the kind of action in all three slots
     (send, accept, assign, perform; a performed action is written `entry onEntry;`)
  2. structure: reads (substates, isParallel) x state (sequential with substates, parallel)
  3. transitions: reads (source, target, triggerPayload, guardKind, effectKind) x transition
     (with trigger, guard and effect; a bare `first a then b`)

Reads:
  entryKind / doKind / exitKind  metaclass of StateUsage::entryAction / doAction / exitAction
  substates       sorted names of the owned features that are StateUsages
  isParallel      StateUsage::isParallel
  source, target  TransitionUsage::source / target (qualified names)
  triggerPayload  type of the payload parameter of TransitionUsage::triggerAction; null without one
  guardKind       metaclass of TransitionUsage::guardExpression; null without one
  effectKind      metaclass of TransitionUsage::effectAction; null without one
"""
from genlib import Matrix

READ_COL = {"entryKind": "can get entry action", "doKind": "can get do action", "exitKind": "can get exit action",
            "substates": "can list substates", "isParallel": "can tell parallel", "source": "can get source",
            "target": "can get target", "triggerPayload": "can get trigger", "guardKind": "can get guard",
            "effectKind": "can get effect"}
ACT_COL = {"send": "send action", "accept": "accept action", "assign": "assign action", "perform": "perform action"}
STATE_COL = {"seq": "sequential state", "par": "parallel state"}
TRANS_COL = {"full": "transition with trigger, guard, effect", "bare": "bare transition"}
LOC_COL = {"DEF": "in state def", "EXH": "through exhibit state", "L3": "through typing usage"}
THROUGH = {"DEF": None, "EXH": ["C30::Device::ex"], "L3": ["C30::device", "C30::Device::ex"]}
C = "C30::Ctl::"
ACT = {"send": ("sSend", "SendActionUsage"), "accept": ("sAccept", "AcceptActionUsage"),
       "assign": ("sAssign", "AssignmentActionUsage"), "perform": ("sPerform", "PerformActionUsage")}
STATE = {"seq": ("seq", ["s1", "s2"], False), "par": ("par", ["r1", "r2"], True)}
TRANS = {"full": ("t1", C + "sSend", C + "sAssign", "C30::Sig", "OperatorExpression", "AssignmentActionUsage"),
         "bare": ("t2", C + "sAssign", C + "sPerform", None, None, None)}

m = Matrix("C30", "states and transitions", "models/C30.sysml",
           list(READ_COL.values()) + list(ACT_COL.values()) + list(STATE_COL.values()) + list(TRANS_COL.values())
           + list(LOC_COL.values()),
           description="State entry/do/exit actions, state structure, and transitions.",
           notes={"reads": __doc__.split("Reads:")[1].strip(),
                  "model": "a case may name its own model; it overrides the matrix's model for that case",
                  "through": "a path: each element is read as a member visible in the previous one"})
for read in ["entryKind", "doKind", "exitKind"]:
    for act, (state, metaclass) in ACT.items():
        for loc in LOC_COL:
            if act == "accept":
                through = [p.replace("C30::", "C30Accept::") for p in THROUGH[loc]] if THROUGH[loc] else None
                m.add({READ_COL[read], ACT_COL[act], LOC_COL[loc]}, read, "C30Accept::Ctl::" + state, metaclass,
                      through, model="models/C30-accept.sysml")
            else:
                m.add({READ_COL[read], ACT_COL[act], LOC_COL[loc]}, read, C + state, metaclass, THROUGH[loc])
for read in ["substates", "isParallel"]:
    for st, (state, subs, parallel) in STATE.items():
        for loc in LOC_COL:
            m.add({READ_COL[read], STATE_COL[st], LOC_COL[loc]}, read, C + state,
                  subs if read == "substates" else parallel, THROUGH[loc])
for read in ["source", "target", "triggerPayload", "guardKind", "effectKind"]:
    for tr, (name, src, tgt, trig, guard, effect) in TRANS.items():
        for loc in LOC_COL:
            expect = {"source": src, "target": tgt, "triggerPayload": trig, "guardKind": guard, "effectKind": effect}[read]
            m.add({READ_COL[read], TRANS_COL[tr], LOC_COL[loc]}, read, C + name, expect, THROUGH[loc])
m.write("gen_c30.py")
