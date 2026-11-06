#!/usr/bin/env python3
"""Matrix C10 - action parameters and their bound values.

Two blocks, each a full cross product:
  1. value reads x value variant (literal, feature reference, feature chain, operator expression, none)
       x location (perform action in part def, action usage in part def, through typing usage,
                   through usage of specialized def)
  2. parameter reads x parameter direction (in, out, inout)
       x location (action def, through specializing action def, through perform action,
                   through typing usage)

Value reads compare the structure of the parameter's bound expression (the value of
its owned FeatureValue membership), not its text:
  valueKind        metaclass of the expression (LiteralRational, FeatureReferenceExpression,
                   FeatureChainExpression, OperatorExpression); null without a value
  valueOperator    OperatorExpression::operator; null for other expressions (a FeatureChainExpression
                   specializes OperatorExpression with operator ".")
  valueReferences  referenced features, collected left to right, each in chain form (a
                   FeatureReferenceExpression gives [referent]; a FeatureChainExpression
                   gives its source's chain extended by its targetFeature); [] for a literal
  valueText        the expression's source text, where an API can return it
Parameter reads: name (Element::name), direction (Feature::direction), type (first of Feature::type).
"""
from genlib import Matrix

VALUE_READS = ["valueKind", "valueOperator", "valueReferences", "valueText"]
PARAM_READS = ["name", "direction", "type"]
READ_COL = {"valueKind": "can get value kind", "valueOperator": "can get operator",
            "valueReferences": "can get referenced features", "valueText": "can get value text",
            "name": "can read name", "direction": "can get direction", "type": "can get type"}
VAR_COL = {"literal": "literal", "ref": "feature reference", "chain": "feature chain",
           "op": "operator expression", "none": "no value"}
DIR_COL = {"in": "in parameter", "out": "out parameter", "inout": "inout parameter"}
LOC_COL = {"perform": "perform action in part def", "action": "action usage in part def",
           "L3": "read through typing usage", "L4": "read through usage of specialized def",
           "ADEF": "action def", "ASPEC": "through specializing action def"}

CHAIN = ["C10::Motor::powerPort", "C10::PowerPort::power"]
VALUES = {  # variant -> (parameter, kind, operator, references, text)
    "literal": ("pLiteral", "LiteralRational", None, [], "0.5"),
    "ref": ("pRef", "FeatureReferenceExpression", None, [["C10::Motor::level"]], "level"),
    "chain": ("pChain", "FeatureChainExpression", ".", [CHAIN], "powerPort.power"),  # a FeatureChainExpression is an OperatorExpression with operator "."
    "op": ("pOp", "OperatorExpression", "*", [CHAIN], "powerPort.power * 2.0"),
    "none": ("pNone", None, None, None, None),
}
ACTION = {"perform": ("consume", None), "action": ("boost", None),
          "L3": ("consume", ["C10::motor"]), "L4": ("consume", ["C10::subMotor"])}
PARAM = {"in": "pNone", "out": "heat", "inout": "mode"}

m = Matrix("C10", "action parameters and bound values", "models/C10.sysml",
           list(READ_COL.values()) + list(VAR_COL.values()) + list(DIR_COL.values()) + list(LOC_COL.values()),
           description="Bound values of action parameters (by expression structure), and parameter reads.",
           notes={"reads": __doc__.split("Value reads")[1].strip(),
                  "through": "a path: each element is read as a member visible in the previous one"})
for read in VALUE_READS:
    for var in VAR_COL:
        for loc in ["perform", "action", "L3", "L4"]:
            param, kind, op, refs, text = VALUES[var]
            action, path = ACTION[loc]
            action_qn = f"C10::Motor::{action}"
            if var == "none":
                # not redefined in the action: the inherited parameter of Consume, read through it
                el, through = f"C10::Consume::{param}", (path or []) + [action_qn]
            else:
                # redefined in the action usage, owned by it (read through the action when a path is given)
                el, through = f"{action_qn}::{param}", (path + [action_qn] if path else None)
            expect = {"valueKind": kind, "valueOperator": op, "valueReferences": refs, "valueText": text}[read]
            m.add({READ_COL[read], VAR_COL[var], LOC_COL[loc]}, read, el, expect, through)
for read in PARAM_READS:
    for d in DIR_COL:
        for loc in ["ADEF", "ASPEC", "perform", "L3"]:
            param = PARAM[d]
            el = f"C10::Consume::{param}"
            through = {"ADEF": None, "ASPEC": ["C10::SubConsume"], "perform": ["C10::Motor::consume"],
                       "L3": ["C10::motor", "C10::Motor::consume"]}[loc]
            expect = {"name": param, "direction": d, "type": "ScalarValues::Real"}[read]
            m.add({READ_COL[read], DIR_COL[d], LOC_COL[loc]}, read, el, expect, through)
m.write("gen_c10.py")
