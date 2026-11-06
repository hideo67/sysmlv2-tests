#!/usr/bin/env python3
"""Matrix C01 - behavioral definitions.

Full cross product: reads x definition kind (action, state, calc, constraint, requirement,
use case, analysis, verification) x location (DL1 the definition itself, inherited by a
specializing definition `SubX :> X`).

Reads:
  name        Element::name
  kind        the metaclass
  isAbstract  Type::isAbstract
  parameters  sorted [direction, name] of Type::directedFeature (owned and inherited, from the
              standard library too; an unnamed feature has name "")
  result      name of the result parameter (Function::result: calc, constraint, requirement,
              use case, analysis and verification definitions are functions); null otherwise
  subject     name of the subject parameter (RequirementDefinition/CaseDefinition::
              subjectParameter); null otherwise
Cases marked `libraryDependent` expect members inherited from the standard library; that part
was taken from the Pilot Implementation (library 0.64.0) and checked against the library source.
"""
from genlib import Matrix

READS = ["name", "kind", "isAbstract", "parameters", "result", "subject"]
READ_COL = {"name": "can read name", "kind": "can get kind", "isAbstract": "can tell abstract",
            "parameters": "can list parameters", "result": "can get result", "subject": "can get subject"}
KINDS = {  # base name -> (metaclass, own parameters, subject)
    "Act": ("ActionDefinition", [["in", "x"], ["out", "y"]], None),
    "St": ("StateDefinition", [["in", "x"]], None),
    "Calc": ("CalculationDefinition", [["in", "x"], ["out", "r"]], None),
    "Cons": ("ConstraintDefinition", [["in", "x"]], None),
    "Req": ("RequirementDefinition", [["in", "s"], ["in", "x"]], "s"),
    "UC": ("UseCaseDefinition", [["in", "s"]], "s"),
    "An": ("AnalysisCaseDefinition", [["in", "s"], ["out", "r"]], "s"),
    "Ver": ("VerificationCaseDefinition", [["in", "s"]], "s"),
}
KIND_COL = {"Act": "action def", "St": "state def", "Calc": "calc def", "Cons": "constraint def",
            "Req": "requirement def", "UC": "use case def", "An": "analysis def", "Ver": "verification def"}
LOC_COL = {"DL1": "definition itself", "DINH": "inherited by specializing def"}
# Directed features inherited from the library, and the result parameter's name: the Pilot's
# answer (library 0.64.0), checked against the library source: `return result` in
# Performances.kerml (evaluations, constraints) and Requirements.sysml, `return verdict ... :>> result`
# in VerificationCases.sysml. A calc or analysis def's own `return r` redefines `result`.
LIB_PARAMS = {"Act": [], "St": [], "Calc": [], "Cons": [["out", "result"]], "Req": [["out", "result"]],
              "UC": [["out", "result"]], "An": [], "Ver": [["out", "verdict"]]}
RESULT = {"Act": None, "St": None, "Calc": "r", "Cons": "result", "Req": "result", "UC": "result",
          "An": "r", "Ver": "verdict"}
FROM_LIBRARY = {"Cons", "Req", "UC", "Ver"}   # kinds whose parameters/result come partly from the library

m = Matrix("C01", "behavioral definitions", "models/C01.sysml",
           list(READ_COL.values()) + list(KIND_COL.values()) + list(LOC_COL.values()),
           description="Behavioral definitions of each kind, and their parameters, result and subject.",
           notes={"reads": __doc__.split("Reads:")[1].strip()})
for read in READS:
    for k, (metaclass, own, subject) in KINDS.items():
        for loc in LOC_COL:
            name = k if loc == "DL1" else f"Sub{k}"
            extra = {}
            if read == "parameters":
                expect = sorted(own + LIB_PARAMS[k])
            elif read == "result":
                expect = RESULT[k]
            else:
                expect = {"name": name, "kind": metaclass, "isAbstract": False, "subject": subject}[read]
            if read in ("parameters", "result") and k in FROM_LIBRARY:
                extra["libraryDependent"] = True
            m.add({READ_COL[read], KIND_COL[k], LOC_COL[loc]}, read, f"C01::{name}", expect, **extra)
m.write("gen_c01.py")
