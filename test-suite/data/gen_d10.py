#!/usr/bin/env python3
"""Matrix D10 - metadata annotations.

Full cross product: reads x annotation form (prefix `#M`, body `@M { ... }`,
`metadata m : M about x { ... }` owned elsewhere) x annotated site (part def, part usage
in part def, state usage in state def, action parameter, part usage read through a
typing usage).

Reads (the annotations of an element are the MetadataUsages whose annotatedElement
includes it, wherever they are owned):
  metadataDefs      sorted qualified names of those MetadataUsages' metadataDefinition
  metadataValue     literal value of the annotation's own feature redefining `severity`
                    (null when the annotation does not redefine it, as with the prefix form)
  annotatedElement  the annotation's annotatedElement (qualified names)
"""
from genlib import Matrix

READS = ["metadataDefs", "metadataValue", "annotatedElement"]
READ_COL = {"metadataDefs": "can find annotations", "metadataValue": "can get metadata value",
            "annotatedElement": "can get annotated element"}
FORM_COL = {"P": "prefix #M", "B": "body @M", "A": "metadata about"}
SITE_COL = {"def": "on part def", "usage": "on part usage", "state": "on state",
            "param": "on action parameter", "L3": "read through typing usage"}
VALUE = {"P": None, "B": 3, "A": 2}


def site(s, form):
    """(element, through) of the annotated element."""
    return {"def": (f"D10::Pump{form}", None), "usage": (f"D10::Pump::motor{form}", None),
            "state": (f"D10::PumpStates::overheated{form}", None),
            "param": (f"D10::PumpFluid::pressure{form}", None),
            "L3": (f"D10::Pump::motor{form}", ["D10::pump"])}[s]


m = Matrix("D10", "metadata annotations", "models/D10.sysml",
           list(READ_COL.values()) + list(FORM_COL.values()) + list(SITE_COL.values()),
           description="Metadata annotations in their three forms, on several kinds of element.",
           notes={"reads": __doc__.split("Reads (")[1].strip(),
                  "through": "a path: each element is read as a member visible in the previous one"})
for read in READS:
    for form in FORM_COL:
        for s in SITE_COL:
            el, through = site(s, form)
            expect = {"metadataDefs": ["D10::FailureMode"], "metadataValue": VALUE[form],
                      "annotatedElement": [el]}[read]
            m.add({READ_COL[read], FORM_COL[form], SITE_COL[s]}, read, el, expect, through)
m.write("gen_d10.py")
