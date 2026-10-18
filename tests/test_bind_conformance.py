"""Grammar conformance: the cases in tests/fixtures/bindings/conformance are shared with dcs-project (deck-vars.js)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opord_builder import bind

DIR = Path(__file__).resolve().parent / "fixtures" / "bindings" / "conformance"
VARS = json.loads((DIR / "vars.json").read_text(encoding="utf-8"))
CASES = json.loads((DIR / "expected.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["template"] for c in CASES])
def test_conformance(case):
    doc = {"extensions": {bind.DATA: {"vars": VARS}}, "v": case["template"]}
    out, errors, _ = bind.resolve_document(doc, DIR / "doc.json")
    messages = [e.message for e in errors]
    if "error" in case:
        assert any(case["error"] in m for m in messages), messages
    else:
        assert not errors, messages
        assert out["v"] == case["value"] and type(out["v"]) is type(case["value"])
