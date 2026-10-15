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
    CAPTrackDocument,
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

def test_cap_track_document_validates():
    doc = CAPTrackDocument.model_validate({
        "kind": "cap_tracks",
        "meta": {"title": "Test CAP"},
        "entries": [
            {
                "name": "ANCHOR 1",
                "anchor_point": "32UMA090320",
                "altitude_floor_ft": 20000,
                "altitude_ceiling_ft": 28000,
                "controller_callsign": "MAGIC",
                "primary_freq": "251.0 AM",
            }
        ],
    })
    assert doc.kind == "cap_tracks"
    assert doc.entries[0].name == "ANCHOR 1"


def test_unknown_kind_rejected():
    assert DATA_SOURCE_REGISTRY.get("bogus") is None
    assert "cap_tracks" in DATA_SOURCE_REGISTRY
    # JPITL, TST and HPT are authored in Annex D (and exported to OpenAIX); no standalone documents
    for retired in ("jpitl", "tst", "hpt"):
        assert retired not in DATA_SOURCE_REGISTRY


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
    # Write a standalone CAP-track data-source file
    jpitl_file = tmp_path / "cap.yaml"
    jpitl_file.write_text(
        yaml.dump({
            "kind": "cap_tracks",
            "meta": {"title": "Test CAP for E2E"},
            "entries": [
                {
                    "name": "E2E Track Alpha",
                    "anchor_point": "32UMA999888",
                    "altitude_floor_ft": 20000,
                    "altitude_ceiling_ft": 28000,
                    "controller_callsign": "MAGIC",
                    "primary_freq": "251.0 AM",
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
        "  - letter: C\n"
        "    typed_body:\n"
        "      letter: C\n"
        "data_sources:\n"
        "  - source: cap.yaml\n"
        "    target: annexes.C.typed_body.airspace_control.cap_tracks\n",
        encoding="utf-8",
    )

    opord = load_opord(main)
    annex_c = next(a for a in opord.annexes if a.letter == "C")
    assert annex_c.typed_body is not None
    tracks = annex_c.typed_body.airspace_control.cap_tracks
    assert len(tracks) == 1
    assert tracks[0].name == "E2E Track Alpha"


# ---------------------------------------------------------------------------
# Variable interop test
# ---------------------------------------------------------------------------

def test_data_source_receives_parent_variables(tmp_path: Path):
    # CAP file referencing a variable from the parent OPORD
    cap_file = tmp_path / "cap_vars.yaml"
    cap_file.write_text(
        "kind: cap_tracks\n"
        "meta:\n"
        "  title: CAP with vars\n"
        "entries:\n"
        "  - name: '{{ op_name }} track'\n"
        "    anchor_point: 32UMA111222\n"
        "    altitude_floor_ft: 20000\n"
        "    altitude_ceiling_ft: 28000\n"
        "    controller_callsign: MAGIC\n"
        "    primary_freq: 251.0 AM\n",
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
        "  - letter: C\n"
        "    typed_body:\n"
        "      letter: C\n"
        "data_sources:\n"
        "  - source: cap_vars.yaml\n"
        "    target: annexes.C.typed_body.airspace_control.cap_tracks\n",
        encoding="utf-8",
    )

    opord = load_opord(main)
    annex_c = next(a for a in opord.annexes if a.letter == "C")
    tracks = annex_c.typed_body.airspace_control.cap_tracks
    assert len(tracks) == 1
    assert tracks[0].name == "TEST OP track"


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
    """An OPORD with inline CAP tracks AND external data source entries
    should load with both sets combined into one list."""
    source = tmp_path / "ext_cap.yaml"
    source.write_text(
        "kind: cap_tracks\n"
        "meta:\n"
        "  title: External CAP\n"
        "entries:\n"
        "  - name: EXT-001\n"
        "    anchor_point: 32UMA000000\n"
        "    altitude_floor_ft: 20000\n"
        "    altitude_ceiling_ft: 28000\n"
        "    controller_callsign: MAGIC\n"
        "    primary_freq: 251.0 AM\n",
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
        "  - letter: C\n"
        "    typed_body:\n"
        "      letter: C\n"
        "      airspace_control:\n"
        "        cap_tracks:\n"
        "          - name: INLINE-001\n"
        "            anchor_point: 32UMA111111\n"
        "            altitude_floor_ft: 20000\n"
        "            altitude_ceiling_ft: 28000\n"
        "            controller_callsign: MAGIC\n"
        "            primary_freq: 251.0 AM\n"
        "data_sources:\n"
        "  - source: ext_cap.yaml\n"
        "    target: annexes.C.typed_body.airspace_control.cap_tracks\n",
        encoding="utf-8",
    )

    opord = load_opord(main)
    annex_c = next(a for a in opord.annexes if a.letter == "C")
    tracks = annex_c.typed_body.airspace_control.cap_tracks
    assert len(tracks) == 2
    assert tracks[0].name == "INLINE-001"
    assert tracks[1].name == "EXT-001"
