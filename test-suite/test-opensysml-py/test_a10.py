"""Matrix A10 (part usages) against the OpenSysML Python client."""
import json
import os
from pathlib import Path

import opensysml
import pytest

DATA = Path(__file__).resolve().parents[1] / "data"
SPEC = json.loads((DATA / "cases" / "A10.json").read_text())

# The service binary is the locally built one, never a downloaded release.
os.environ.setdefault("OPENSYSML_BINARY", str(
    Path(__file__).resolve().parents[2] / "OpenSysML" / "bin" / "sysml-grpc"))


class Unsupported(Exception):
    """The API offers no way to obtain this information."""


@pytest.fixture(scope="module")
def model():
    m = opensysml.loads((DATA / SPEC["model"]).read_text())
    assert m.ok, m.diagnostics
    return m


def _sym(model, element):
    s = model.get(element)
    assert s is not None, f"no symbol {element}"
    return s


def do_check(model, check, element, through=None):
    if check in ("isComposite", "isReference"):
        # Symbol has no such flag, and the query API does not know the property.
        try:
            model.query(scope=[element], select=[check])
        except opensysml.errors.InvalidRequestError as e:
            raise Unsupported(f"query API: {e}".split(";")[0])
        raise AssertionError("query accepted the property; extend the adapter")
    if check == "unnamedPartCount":
        rows = model.query(scope=[through or element])
        return sum(1 for r in rows if r.type == "PartUsage"
                   and r.properties.get("owner") == element and "name" not in r.properties)
    if through:
        # the member as seen from the usage: only what the usage's Symbol lists
        visible = {c.id: c for c in _sym(model, through).children()}
        visible.update({c.id: c for c in _sym(model, through).parts()})
        if element not in visible:
            return f"<{element} not visible through {through}>"
        s = visible[element]
    else:
        s = _sym(model, element)
    if check == "name":
        return s.name
    if check == "type":
        if s.type_facts is None:
            raise Unsupported("no type_facts")
        return s.type_facts.resolved_id
    raise AssertionError(f"unknown check {check}")


@pytest.mark.parametrize("case", SPEC["cases"], ids=lambda c: c["id"])
def test_case(model, case):
    try:
        actual = do_check(model, case["check"], case["element"], case.get("through"))
    except Unsupported as e:
        pytest.skip(f"UNSUPPORTED: {e}")
    assert actual == case["expect"]
