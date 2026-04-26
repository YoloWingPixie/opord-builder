"""Tests for the data-source binding and merge system."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from opord_builder.merge import _set_at_path
from opord_builder.renderer import load_opord
from opord_builder.schema.data_sources import (
    DATA_SOURCE_REGISTRY,
    DataSourceMeta,
    HPTDocument,
    JPITLDocument,
    TSTDocument,
)


# ---------------------------------------------------------------------------
# _set_at_path unit tests
# ---------------------------------------------------------------------------

def test_set_at_path_simple_key():
    data = {}
    _set_at_path(data, "foo", 42)
    assert data == {"foo": 42}


def test_set_at_path_nested():
    data = {}
    _set_at_path(data, "a.b.c", "deep")
    assert data == {"a": {"b": {"c": "deep"}}}


def test_set_at_path_annexes_find_existing():
    data = {
        "annexes": [
            {"letter": "A", "body": "alpha"},
            {"letter": "D", "body": "fires"},
        ],
    }
    _set_at_path(data, "annexes.D.typed_body.jpitl", ["entry1"])
    annex_d = next(a for a in data["annexes"] if a["letter"] == "D")
    assert annex_d["typed_body"]["jpitl"] == ["entry1"]
    # Original body untouched
    assert annex_d["body"] == "fires"


def test_set_at_path_annexes_create_missing():
    data = {"annexes": [{"letter": "A", "body": "alpha"}]}
    _set_at_path(data, "annexes.D.typed_body.jpitl", ["entry1"])
    letters = [a["letter"] for a in data["annexes"]]
    assert "D" in letters
    annex_d = next(a for a in data["annexes"] if a["letter"] == "D")
    assert annex_d["typed_body"]["jpitl"] == ["entry1"]


def test_set_at_path_typed_body_injects_letter():
    data = {"annexes": [{"letter": "D"}]}
    _set_at_path(data, "annexes.D.typed_body.jpitl", ["entry1"])
    annex_d = data["annexes"][0]
    assert annex_d["typed_body"]["letter"] == "D"
    assert annex_d["typed_body"]["jpitl"] == ["entry1"]


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------

def test_jpitl_document_validates():
    doc = JPITLDocument.model_validate({
        "kind": "jpitl",
        "meta": {"title": "Test JPITL"},
        "entries": [
            {
                "target_number": "TGT 0001",
                "priority_rank": 1,
                "target_name": "ENY CP",
                "target_description": "Command post",
                "category": "C2",
                "location": "32UMA123456",
                "component_tasked": "LAND",
                "desired_effect": "DESTROY",
                "engagement_guidance": "Fire at will",
                "approval_authority": "BN CDR",
            }
        ],
    })
    assert doc.kind == "jpitl"
    assert len(doc.entries) == 1
    assert doc.entries[0].target_number == "TGT 0001"


def test_tst_document_validates():
    doc = TSTDocument.model_validate({
        "kind": "tst",
        "meta": {"title": "Test TST"},
        "entries": [
            {
                "tst_number": "TST-01",
                "priority_class": "TST-1",
                "category": "WMD",
                "target_description": "Mobile launcher",
                "expected_activity": "TEL erects for launch",
                "pid_standard": "2 independent sensors",
                "engagement_authority": "JFACC",
            }
        ],
    })
    assert doc.kind == "tst"
    assert len(doc.entries) == 1
    assert doc.entries[0].tst_number == "TST-01"


def test_hpt_document_validates():
    doc = HPTDocument.model_validate({
        "kind": "hpt",
        "meta": {"title": "Test HPT"},
        "entries": [
            {
                "priority_rank": 1,
                "category": "FIRES",
                "target_description": "Artillery battery",
                "signature": "Thermal hot spots",
                "engagement_guidance": "Suppress on detection",
            }
        ],
    })
    assert doc.kind == "hpt"
    assert len(doc.entries) == 1
    assert doc.entries[0].priority_rank == 1


def test_unknown_kind_rejected():
    assert DATA_SOURCE_REGISTRY.get("bogus") is None
    assert "jpitl" in DATA_SOURCE_REGISTRY
    assert "tst" in DATA_SOURCE_REGISTRY
    assert "hpt" in DATA_SOURCE_REGISTRY


def test_meta_required_fields():
    """meta.title is required; all other fields are optional."""
    from pydantic import ValidationError

    # Missing title should fail
    with pytest.raises(ValidationError):
        DataSourceMeta.model_validate({})

    # Title alone is sufficient
    meta = DataSourceMeta.model_validate({"title": "Minimal"})
    assert meta.title == "Minimal"
    assert meta.classification is None
    assert meta.as_of_dtg is None
    assert meta.approved_by is None
    assert meta.version is None
    assert meta.notes is None


# ---------------------------------------------------------------------------
# End-to-end integration test
# ---------------------------------------------------------------------------

def test_opord_with_data_sources_renders(tmp_path: Path):
    # Write a standalone JPITL data-source file
    jpitl_file = tmp_path / "jpitl.yaml"
    jpitl_file.write_text(
        yaml.dump({
            "kind": "jpitl",
            "meta": {"title": "Test JPITL for E2E"},
            "entries": [
                {
                    "target_number": "TGT 9001",
                    "priority_rank": 1,
                    "target_name": "E2E Target Alpha",
                    "target_description": "End-to-end test target",
                    "category": "C2",
                    "location": "32UMA999888",
                    "component_tasked": "LAND",
                    "desired_effect": "NEUTRALIZE",
                    "engagement_guidance": "Fire for effect",
                    "approval_authority": "BN CDR",
                },
            ],
        }),
        encoding="utf-8",
    )

    # Write main OPORD with data_sources binding
    main = tmp_path / "opord.yaml"
    main.write_text(
        "header:\n"
        "  classification: UNCLASSIFIED\n"
        "  issuing_headquarters: HQ\n"
        "  place_of_issue: X\n"
        "  dtg: 010000ZJAN26\n"
        "  operation_order_number: '99'\n"
        "  operation_name: DATASRC\n"
        "  time_zone: ZULU\n"
        "mission: Test data source merge.\n"
        "annexes:\n"
        "  - letter: D\n"
        "    typed_body:\n"
        "      letter: D\n"
        "data_sources:\n"
        "  - source: jpitl.yaml\n"
        "    target: annexes.D.typed_body.jpitl\n",
        encoding="utf-8",
    )

    opord = load_opord(main)
    annex_d = next(a for a in opord.annexes if a.letter == "D")
    assert annex_d.typed_body is not None
    jpitl = annex_d.typed_body.jpitl
    assert len(jpitl) == 1
    assert jpitl[0].target_number == "TGT 9001"
    assert jpitl[0].target_name == "E2E Target Alpha"


# ---------------------------------------------------------------------------
# Variable interop test
# ---------------------------------------------------------------------------

def test_data_source_receives_parent_variables(tmp_path: Path):
    # JPITL file referencing a variable from the parent OPORD
    jpitl_file = tmp_path / "jpitl_vars.yaml"
    jpitl_file.write_text(
        "kind: jpitl\n"
        "meta:\n"
        "  title: JPITL with vars\n"
        "entries:\n"
        "  - target_number: TGT 7777\n"
        "    priority_rank: 1\n"
        "    target_name: '{{ op_name }} target'\n"
        "    target_description: Test variable interop\n"
        "    category: FIRES\n"
        "    location: 32UMA111222\n"
        "    component_tasked: LAND\n"
        "    desired_effect: SUPPRESS\n"
        "    engagement_guidance: Suppress on contact\n"
        "    approval_authority: BCT CDR\n",
        encoding="utf-8",
    )

    main = tmp_path / "opord.yaml"
    main.write_text(
        "variables:\n"
        "  op_name: TEST OP\n"
        "header:\n"
        "  classification: UNCLASSIFIED\n"
        "  issuing_headquarters: HQ\n"
        "  place_of_issue: X\n"
        "  dtg: 010000ZJAN26\n"
        "  operation_order_number: '99'\n"
        "  operation_name: '{{ op_name }}'\n"
        "  time_zone: ZULU\n"
        "mission: Test variable pass-through.\n"
        "annexes:\n"
        "  - letter: D\n"
        "    typed_body:\n"
        "      letter: D\n"
        "data_sources:\n"
        "  - source: jpitl_vars.yaml\n"
        "    target: annexes.D.typed_body.jpitl\n",
        encoding="utf-8",
    )

    opord = load_opord(main)
    annex_d = next(a for a in opord.annexes if a.letter == "D")
    jpitl = annex_d.typed_body.jpitl
    assert len(jpitl) == 1
    assert jpitl[0].target_name == "TEST OP target"


def test_set_at_path_appends_to_existing_list():
    """Inline entries and data-source entries combine into one list."""
    data = {
        "annexes": [
            {
                "letter": "D",
                "typed_body": {
                    "letter": "D",
                    "jpitl": [{"target_number": "INLINE-001"}],
                },
            }
        ]
    }
    _set_at_path(data, "annexes.D.typed_body.jpitl", [{"target_number": "EXT-001"}])
    jpitl = data["annexes"][0]["typed_body"]["jpitl"]
    assert len(jpitl) == 2
    assert jpitl[0]["target_number"] == "INLINE-001"
    assert jpitl[1]["target_number"] == "EXT-001"


def test_inline_plus_external_sources_combine(tmp_path: Path):
    """An OPORD with inline JPITL entries AND external data source entries
    should render with both sets combined into one table."""
    source = tmp_path / "ext_jpitl.yaml"
    source.write_text(
        "kind: jpitl\n"
        "meta:\n"
        "  title: External JPITL\n"
        "entries:\n"
        "  - target_number: EXT-001\n"
        "    priority_rank: 2\n"
        "    target_name: External target\n"
        "    target_description: From data source\n"
        "    category: FIRES\n"
        "    location: 32UMA000000\n"
        "    component_tasked: LAND\n"
        "    desired_effect: DESTROY\n"
        "    engagement_guidance: External guidance\n"
        "    approval_authority: BN CDR\n",
        encoding="utf-8",
    )
    main = tmp_path / "main.yaml"
    main.write_text(
        "header:\n"
        "  classification: UNCLASSIFIED\n"
        "  issuing_headquarters: Test HQ\n"
        "  place_of_issue: Test Location\n"
        "  dtg: 011200ZJAN26\n"
        "  operation_order_number: '26-01'\n"
        "  operation_name: TEST\n"
        "  time_zone: ZULU\n"
        "mission: Test mission\n"
        "annexes:\n"
        "  - letter: D\n"
        "    typed_body:\n"
        "      letter: D\n"
        "      jpitl:\n"
        "        - target_number: INLINE-001\n"
        "          priority_rank: 1\n"
        "          target_name: Inline target\n"
        "          target_description: From OPORD inline\n"
        "          category: C2\n"
        "          location: 32UMA111111\n"
        "          component_tasked: LAND\n"
        "          desired_effect: NEUTRALIZE\n"
        "          engagement_guidance: Inline guidance\n"
        "          approval_authority: BCT CDR\n"
        "data_sources:\n"
        "  - source: ext_jpitl.yaml\n"
        "    target: annexes.D.typed_body.jpitl\n",
        encoding="utf-8",
    )

    opord = load_opord(main)
    annex_d = next(a for a in opord.annexes if a.letter == "D")
    jpitl = annex_d.typed_body.jpitl
    assert len(jpitl) == 2
    assert jpitl[0].target_number == "INLINE-001"
    assert jpitl[1].target_number == "EXT-001"
