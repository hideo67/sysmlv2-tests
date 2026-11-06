#!/usr/bin/env python3
"""Matrix D20 - documentation, comments and textual representations.

Full cross product: reads x form (`doc /* */` in the body, `comment /* */` in the body,
`comment c about X /* */` owned elsewhere, `rep language "text" /* */` in the body) x site
(package, part def, part usage in a part def, part usage read through a typing usage).

Reads (bodies compared with surrounding whitespace trimmed):
  documentation          sorted bodies of Element::documentation
  comments               sorted bodies of the Comments (not Documentation) whose annotatedElement
                         includes the element, wherever they are owned (a body comment annotates
                         its owning element)
  textualRepresentation  sorted [language, body] of Element::textualRepresentation
"""
from genlib import Matrix

READS = ["documentation", "comments", "textualRepresentation"]
READ_COL = {"documentation": "can get documentation", "comments": "can find comments",
            "textualRepresentation": "can get textual representation"}
FORM_COL = {"Doc": "doc", "Com": "body comment", "About": "comment about", "Rep": "rep"}
SITE_COL = {"pkg": "on package", "def": "on part def", "usage": "on part usage", "L3": "read through typing usage"}
SITE = {  # site -> (element prefix, through, word used in the bodies)
    "pkg": ("D20::P", None, "package"), "def": ("D20::Def", None, "def"),
    "usage": ("D20::Holder::u", None, "usage"), "L3": ("D20::Holder::u", ["D20::holder"], "usage"),
}

m = Matrix("D20", "documentation, comments and textual representations", "models/D20.sysml",
           list(READ_COL.values()) + list(FORM_COL.values()) + list(SITE_COL.values()),
           description="Documentation, comments and textual representations on several kinds of element.",
           notes={"reads": __doc__.split("Reads (")[1].strip(),
                  "through": "a path: each element is read as a member visible in the previous one"})
for read in READS:
    for form in FORM_COL:
        for site in SITE_COL:
            prefix, through, word = SITE[site]
            expect = {
                "documentation": [f"{word} doc"] if form == "Doc" else [],
                "comments": [f"{word} comment"] if form == "Com" else [f"{word} about"] if form == "About" else [],
                "textualRepresentation": [["text", f"{word} rep"]] if form == "Rep" else [],
            }[read]
            m.add({READ_COL[read], FORM_COL[form], SITE_COL[site]}, read, prefix + form, expect, through)
m.write("gen_d20.py")
