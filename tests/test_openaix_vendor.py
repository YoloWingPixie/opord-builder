"""Phase 0: the vendored OpenAIX copy, its registry and validation."""

from __future__ import annotations

import copy
import hashlib
import json
import time
from pathlib import Path

import pytest

from opord_builder.openaix.registry import VENDOR_DIR, registry, schemas
from opord_builder.openaix.validate import validate

EXAMPLES = sorted((VENDOR_DIR / "examples").glob("*/*.json"))


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_examples_found():
    assert {p.parent.name for p in EXAMPLES} == {"minimal", "maximal"}
    assert len(EXAMPLES) > 40


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_vendored_example_validates(path):
    assert [str(e) for e in validate(_load(path))] == []


def test_mutated_identifier_fails_with_pointer():
    doc = copy.deepcopy(_load(VENDOR_DIR / "examples/maximal/ato.json"))
    doc["missions"][0]["id"] = "Bad Id!"
    errors = validate(doc)
    assert any(e.pointer == "/missions/0/id" for e in errors)


def test_unknown_kind_and_schema_are_errors():
    assert validate({"kind": "nope"})[0].pointer == ""
    assert validate({"$schema": "urn:openaix:schema:nope:1"})[0].pointer == ""


def test_bad_datetime_is_checked():
    doc = copy.deepcopy(_load(VENDOR_DIR / "examples/minimal/ato.json"))
    doc["period"]["start"] = "2026-13-45 nonsense"
    assert any(e.pointer == "/period/start" for e in validate(doc))


def test_registry_has_every_id_and_fails_unresolved():
    reg = registry()
    for schema in schemas().values():
        assert reg.get(schema["$id"]) is not None
    from referencing.exceptions import NoSuchResource

    with pytest.raises(NoSuchResource):
        reg.get_or_retrieve("urn:openaix:schema:missing:0")


def test_vendor_sha256_matches():
    manifest = _load(VENDOR_DIR / "VENDOR.json")
    assert manifest["version"] == "0.2.0-draft.1"
    assert len(manifest["commit"]) == 40
    assert manifest["files"]
    for rel, digest in manifest["files"].items():
        assert hashlib.sha256((VENDOR_DIR / rel).read_bytes()).hexdigest() == digest, (
            rel
        )
    on_disk = {
        p.relative_to(VENDOR_DIR).as_posix()
        for p in VENDOR_DIR.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    assert on_disk - {"VENDOR.json"} == set(manifest["files"])


def test_validation_under_one_second():
    biggest = max(EXAMPLES, key=lambda p: p.stat().st_size)
    doc = _load(biggest)
    validate(doc)  # warm the caches (registry is built once per process)
    start = time.perf_counter()
    validate(doc)
    assert time.perf_counter() - start < 1.0
