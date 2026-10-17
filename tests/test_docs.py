"""Generated schema docs: freshness, bundled-schema verdicts, the complete-schema page and `opord docs --check`."""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from opord_builder import docs
from opord_builder.cli import app
from opord_builder.load import read, validate_document
from opord_builder.openaix.validate import FORMAT_CHECKER, pointer

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


@pytest.fixture(scope="module")
def generated():
    return docs.generated()


def bundle_errors(doc):
    validator = Draft202012Validator(
        docs.bundled(doc["kind"], strict=True), format_checker=FORMAT_CHECKER
    )
    return {pointer(e.absolute_path) for e in validator.iter_errors(doc)}


def test_generated_files_are_not_stale(generated):
    stale = [
        str(p)
        for p, text in generated.items()
        if not (REPO / p).is_file() or (REPO / p).read_text(encoding="utf-8") != text
    ]
    assert not stale, f"run `opord docs`: {stale}"


@pytest.mark.parametrize("path", DOCS, ids=lambda p: str(p.relative_to(REPO)))
def test_bundle_verdict_equals_validate_document(path):
    doc = read(path)
    if doc.get("kind") not in docs.KINDS:
        pytest.skip("no bundled schema for this kind")
    assert not validate_document(doc)
    assert not bundle_errors(doc)


def test_bundle_fails_a_mutated_extension_at_the_same_pointer():
    doc = read(REPO / "examples/example_full.yaml")
    bad = copy.deepcopy(doc)
    bad["extensions"]["org.opord-builder.order"]["situation"]["civil_considerations"][
        "areas"
    ] = 7
    want = {e.pointer for e in validate_document(bad)}
    assert want and want <= bundle_errors(bad)


def test_bundles_have_no_dangling_refs():
    for kind in docs.KINDS:
        schema = docs.bundled(kind)
        text = str(schema)
        for ref in set(re.findall(r"'\$ref': '([^']+)'", text)):
            assert ref.startswith("#"), (kind, ref)
            node = schema
            for part in ref[2:].split("/") if ref != "#" else []:
                node = node[part]


def test_complete_schema_is_deterministic():
    assert docs.complete_schema_html() == docs.complete_schema_html()


def test_every_type_has_an_anchor_and_links_resolve():
    page = docs.complete_schema_html()
    ids = set(re.findall(r'id="([^"]+)"', page))
    for name, schema in docs.sources().items():
        assert name in ids
        for def_name in schema.get("$defs", {}):
            assert f"{name}.{def_name}" in ids
    links = set(re.findall(r'href="#([^"]+)"', page))
    assert not links - ids
    reference = docs.reference_html()
    assert (
        not {h for h in re.findall(r'href="complete-schema\.html#([^"]+)"', reference)}
        - ids
    )


def test_docs_check_exits_1_on_a_stale_copy(tmp_path, generated):
    for rel, text in generated.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    runner = CliRunner()
    assert (
        runner.invoke(app, ["docs", "--check", "--out-dir", str(tmp_path)]).exit_code
        == 0
    )
    (tmp_path / "docs/annex_reference.html").write_text("stale", encoding="utf-8")
    result = runner.invoke(app, ["docs", "--check", "--out-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "annex_reference.html" in result.output and "opord docs" in result.output
