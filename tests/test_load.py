"""Native OpenAIX documents: loading, extension validation and round trips."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from opord_builder.load import DocumentError, load_document, read, validate_document

REPO = Path(__file__).resolve().parent.parent
DOCS = sorted(
    p
    for pattern in (
        "examples/**/*.yaml",
        "docs/**/*.yaml",
        "tests/fixtures/openaix/**/*.json",
    )
    for p in REPO.glob(pattern)
)


@pytest.mark.parametrize("path", DOCS, ids=lambda p: str(p.relative_to(REPO)))
def test_every_document_validates_and_round_trips(path):
    doc = load_document(path)
    assert yaml.safe_load(yaml.safe_dump(json.loads(json.dumps(doc)))) == doc


def test_mutated_extension_fails_with_its_pointer():
    doc = read(REPO / "examples/example_full.yaml")
    bad = copy.deepcopy(doc)
    bad["extensions"]["org.opord-builder.order"]["situation"]["civil_considerations"][
        "areas"
    ] = 7
    errors = validate_document(bad)
    assert [e.pointer for e in errors] == [
        "/extensions/org.opord-builder.order/situation/civil_considerations/areas"
    ]


def test_unknown_extension_namespace_is_an_error():
    doc = read(REPO / "examples/example_minimal.yaml")
    doc.setdefault("extensions", {})["org.opord-builder.typo"] = {}
    assert validate_document(doc)[0].pointer == "/extensions/org.opord-builder.typo"


def test_load_document_reports_pointers(tmp_path):
    doc = read(REPO / "examples/example_minimal.yaml")
    doc["order_number"] = ""
    path = tmp_path / "x.yaml"
    path.write_text(yaml.safe_dump(doc))
    with pytest.raises(DocumentError, match="/order_number"):
        load_document(path)


def test_include_resolves_relative_to_the_including_file(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.yaml").write_text("- !include b.yaml\n")
    (tmp_path / "sub" / "b.yaml").write_text("x: 1\n")
    assert read(tmp_path / "sub" / "a.yaml") == [{"x": 1}]


def test_timestamps_stay_text(tmp_path):
    (tmp_path / "t.yaml").write_text("when: 2026-04-18T12:00:00Z\n")
    assert read(tmp_path / "t.yaml") == {"when": "2026-04-18T12:00:00Z"}
