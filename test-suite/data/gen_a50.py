#!/usr/bin/env python3
"""Matrix A50 - unnamed members.

Full cross product: reads x unnamed member (part, attribute, `bind`, `connect`, `flow`,
body metadata `@M;`) x location (owned by a package, owned by a part def, read through a
typing usage of that part def).

Each case locates its member with `unnamed` (the first unnamed member of that metaclass
declared in `element`), so finding it at all is part of every read.
Reads:
  kind         the member's metaclass
  owner        Element::owningNamespace
  idRoundTrip  the identifier the API gives the member finds the same member again
"""
from genlib import Matrix

READS = ["kind", "owner", "idRoundTrip"]
READ_COL = {"kind": "can get kind", "owner": "can get owner", "idRoundTrip": "id round trip"}
MEMBER = {  # member -> (locator metaclass, expected metaclass)
    "part": ("PartUsage", "PartUsage"),
    "attribute": ("AttributeUsage", "AttributeUsage"),
    "bind": ("BindingConnector", "BindingConnectorAsUsage"),
    "connect": ("ConnectionUsage", "ConnectionUsage"),
    "flow": ("Flow", "FlowUsage"),
    "metadata": ("MetadataUsage", "MetadataUsage"),
}
MEMBER_COL = {"part": "unnamed part", "attribute": "unnamed attribute", "bind": "unnamed bind",
              "connect": "unnamed connect", "flow": "unnamed flow", "metadata": "unnamed metadata"}
LOC_COL = {"L1": "appears in package", "L2": "appears in part def", "L3": "read through typing usage"}
LOC = {"L1": ("A50", None), "L2": ("A50::Holder", None), "L3": ("A50::Holder", ["A50::holder"])}

m = Matrix("A50", "unnamed members", "models/A50.sysml",
           list(READ_COL.values()) + list(MEMBER_COL.values()) + list(LOC_COL.values()),
           description="Unnamed members of each kind, located by metaclass and position.",
           notes={"reads": __doc__.split("Reads:")[1].strip(),
                  "unnamed": "locates an unnamed element: {metaclass, index} among the unnamed members "
                             "of that metaclass declared in `element`, in declaration order"})
for read in READS:
    for member, (locator, metaclass) in MEMBER.items():
        for loc in LOC_COL:
            owner, through = LOC[loc]
            expect = {"kind": metaclass, "owner": owner, "idRoundTrip": True}[read]
            m.add({READ_COL[read], MEMBER_COL[member], LOC_COL[loc]}, read, owner, expect, through,
                  unnamed={"metaclass": locator, "index": 0})
m.write("gen_a50.py")
