"""Phase 4: FRAGO <-> OpenAIX."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from opord_builder.cli import app
from opord_builder.openaix.frago import (
    FragoChangeError,
    StaleBaseError,
    apply_changes,
    diff_documents,
    frago_from_openaix,
    frago_to_openaix,
    merge_overlay,
)
from opord_builder.openaix.from_openaix import from_openaix
from opord_builder.openaix.registry import VENDOR_DIR
from opord_builder.openaix.to_openaix import to_openaix
from opord_builder.openaix.validate import validate
from opord_builder.renderer import load_frago, render_frago_markdown
from opord_builder.schema.core import OPORD

ROOT = Path(__file__).resolve().parent.parent
FRAGO_YAML = ROOT / "examples" / "frago_01_iron_strike.yaml"
MAXIMAL = VENDOR_DIR / "examples" / "maximal"
runner = CliRunner()


@pytest.fixture(scope="module")
def loaded():
    return load_frago(FRAGO_YAML)


@pytest.fixture(scope="module")
def exported(loaded):
    frago, base = loaded
    return frago_to_openaix(frago, base)


def test_iron_strike_exports_to_a_valid_frago(exported, loaded):
    _, base = loaded
    doc = exported.frago
    assert validate(doc) == []
    ref = to_openaix(base).opord["meta"]
    assert doc["base_order"] == {"id": ref["id"], "revision": ref["revision"]}
    assert doc["kind"] == "frago"
    assert doc["frago_number"] == "01"
    assert doc["date_time"] == "2026-04-19T01:30:00Z"
    if exported.resources:
        assert validate(exported.resources) == []


def test_changes_are_paragraph_level_replaces(exported):
    changes = exported.frago["changes"]
    assert changes
    paths = {c["path"] for c in changes}
    assert "/execution/coordinating_instructions" in paths
    assert "/situation/enemy_forces" in paths
    assert "/annexes/B" in paths and "/annexes/D" in paths
    for ch in changes:
        depth = len(ch["path"].split("/")) - 1
        assert 2 <= depth <= 3, ch["path"]
        if depth == 3:
            assert ch["path"].startswith("/extensions/")
        assert ch["target"]["kind"] == "opord"
        assert ch["target"]["id"] == exported.frago["base_order"]["id"]
        assert (ch["op"] == "remove") == ("value" not in ch)
    assert {c["op"] for c in changes} <= {"add", "replace", "remove"}
    # paragraphs the FRAGO leaves alone are not touched
    assert not any(
        p.startswith(("/sustainment", "/command_and_signal", "/mission")) for p in paths
    )


def test_reimport_renders_the_same_markdown(exported, loaded):
    frago, base = loaded
    back, warns = frago_from_openaix(
        exported.frago, base, resources=exported.resources, jiptl=exported.jiptl
    )
    assert render_frago_markdown(back, base) == render_frago_markdown(frago, base)
    assert back == frago
    assert not warns


def test_overlay_is_rebuilt_even_without_the_recorded_paths(exported, loaded):
    """A FRAGO written by another tool has no @overlay record: the overlay is the sparse diff."""
    _, base = loaded
    doc = json.loads(json.dumps(exported.frago))
    doc["extensions"]["org.opord-builder.authoring"].pop("@overlay")
    back, _ = frago_from_openaix(
        doc, base, resources=exported.resources, jiptl=exported.jiptl
    )
    md = render_frago_markdown(back, base)
    assert "Enemy Forces" in md and "Coordinating Instructions" in md
    assert back.situation is not None and back.situation.enemy_forces is not None


def test_stale_base_revision_is_an_error(exported, loaded):
    _, base = loaded
    newer = base.model_copy(
        update={"header": base.header.model_copy(update={"revision": "2"})}
    )
    with pytest.raises(StaleBaseError, match="revision"):
        frago_from_openaix(
            exported.frago, newer, resources=exported.resources, jiptl=exported.jiptl
        )
    other = base.model_copy(
        update={
            "header": base.header.model_copy(update={"operation_order_number": "99-99"})
        }
    )
    with pytest.raises(StaleBaseError):
        frago_from_openaix(
            exported.frago, other, resources=exported.resources, jiptl=exported.jiptl
        )


def test_a_change_that_targets_another_revision_is_an_error(exported, loaded):
    _, base = loaded
    doc = json.loads(json.dumps(exported.frago))
    doc["changes"][0]["target"]["revision"] = "9"
    with pytest.raises(StaleBaseError, match="change"):
        frago_from_openaix(
            doc, base, resources=exported.resources, jiptl=exported.jiptl
        )


def test_base_revision_flows_into_the_frago(loaded):
    frago, base = loaded
    rev2 = base.model_copy(
        update={"header": base.header.model_copy(update={"revision": "3"})}
    )
    doc = frago_to_openaix(frago, rev2).frago
    assert doc["base_order"]["revision"] == "3"
    assert {c["target"]["revision"] for c in doc["changes"]} == {"3"}


def test_apply_changes_and_diff_are_inverse():
    base = {"a": {"b": 1, "c": [1, 2]}, "x": {"y": {"z": 1}}, "gone": {"k": 1}}
    merged = {"a": {"b": 2, "c": [1, 2, 3]}, "x": {"y": {"z": 1}}, "new": {"k": 2}}
    ops = diff_documents(base, merged)
    assert [(o, p) for o, p, _ in ops] == [
        ("replace", "/a/b"),
        ("replace", "/a/c"),  # arrays replace whole
        ("add", "/new"),
        ("remove", "/gone"),
    ]
    changes = [
        {"op": o, "path": p, **({"value": v} if o != "remove" else {})}
        for o, p, v in ops
    ]
    assert apply_changes(base, changes) == merged
    with pytest.raises(FragoChangeError):
        apply_changes(base, [{"op": "replace", "path": "/nope/deeper", "value": 1}])
    with pytest.raises(FragoChangeError):
        apply_changes(base, [{"op": "replace", "path": "/a/missing", "value": 1}])


def test_json_pointer_escapes_round_trip():
    base = {"a/b": {"c~d": 1}}
    merged = {"a/b": {"c~d": 2}}
    ops = diff_documents(base, merged)
    assert ops[0][1] == "/a~1b/c~0d"
    assert (
        apply_changes(base, [{"op": "replace", "path": ops[0][1], "value": 2}])
        == merged
    )


def test_merge_overlay_semantics():
    base = {
        "situation": {
            "enemy_forces": {"recent_activities": "old", "capabilities": "kept"}
        },
        "mission": "old mission",
        "annexes": [{"letter": "B", "body": "b"}, {"letter": "D", "body": "d"}],
    }
    over = {
        "situation": {"enemy_forces": {"recent_activities": "new"}},
        "annexes": [{"letter": "D", "body": "d2"}, {"letter": "C", "body": "c"}],
    }
    merged, touched = merge_overlay(base, over)
    assert merged["situation"]["enemy_forces"] == {
        "recent_activities": "new",
        "capabilities": "kept",
    }
    assert merged["mission"] == "old mission"
    assert [a["letter"] for a in merged["annexes"]] == ["B", "C", "D"]
    assert merged["annexes"][2]["body"] == "d2"
    assert touched == [
        "situation.enemy_forces.recent_activities",
        "annexes.D",
        "annexes.C",
    ]


def test_maximal_frago_applies_to_the_maximal_opord():
    """A FRAGO from another tool: its changes are applied to the carried base and the overlay is a sparse diff."""
    opord = json.loads((MAXIMAL / "opord.json").read_text())
    frago = json.loads((MAXIMAL / "frago.json").read_text())
    base, _ = from_openaix(opord)
    back, _ = frago_from_openaix(frago, base, base_order="oir-opord.yaml")
    assert back.frago_number == "01" and back.base_order == "oir-opord.yaml"
    assert back.dtg == "021245ZOCT26"
    assert back.execution is not None
    assert (
        back.execution.tasks_to_subordinate_units[0].tasks[0]
        == "Attack to PL NICKEL (LOA)"
    )
    stale = json.loads(json.dumps(frago))
    stale["base_order"]["revision"] = "7"
    with pytest.raises(StaleBaseError):
        frago_from_openaix(stale, base, base_order="x.yaml")


def test_frago_round_trip_with_new_annex_and_mission(loaded):
    _, base = loaded
    data = {
        "kind": "frago",
        "frago_number": "02",
        "base_order": "example_full.yaml",
        "dtg": "191000ZAPR26",
        "mission": "A revised mission statement.",
        "annexes": [{"letter": "E", "body": "New protection annex."}],
    }
    from opord_builder.schema.core import FRAGO

    frago = FRAGO.model_validate(data)
    bundle = frago_to_openaix(frago, base)
    assert bundle.frago["mission"] == "A revised mission statement."
    paths = {c["path"] for c in bundle.frago["changes"]}
    assert "/mission/statement" in paths and "/annexes/E" in paths
    back, _ = frago_from_openaix(bundle.frago, base, resources=bundle.resources)
    assert back == frago
    assert render_frago_markdown(back, base) == render_frago_markdown(frago, base)


def test_cli_frago_export_import(tmp_path):
    out = tmp_path / "frago"
    r = runner.invoke(app, ["export-openaix", str(FRAGO_YAML), "-o", str(out)])
    assert r.exit_code == 0, r.output
    assert (out / "frago.json").exists()
    r = runner.invoke(app, ["validate-openaix", str(out / "frago.json")])
    assert r.exit_code == 0, r.output
    # a frago needs its base
    yml = tmp_path / "back.yaml"
    r = runner.invoke(app, ["import-openaix", str(out / "frago.json"), "-o", str(yml)])
    assert r.exit_code == 2
    r = runner.invoke(
        app,
        [
            "import-openaix",
            str(out / "frago.json"),
            "--base",
            str(ROOT / "examples" / "example_full.yaml"),
            "-o",
            str(yml),
        ],
    )
    assert r.exit_code == 0, r.output
    data = yaml.safe_load(yml.read_text())
    assert data["kind"] == "frago" and data["frago_number"] == "01"
    assert (tmp_path / data["base_order"]).resolve() == (
        ROOT / "examples" / "example_full.yaml"
    ).resolve()


def test_cli_stale_base_fails(tmp_path):
    out = tmp_path / "frago"
    runner.invoke(app, ["export-openaix", str(FRAGO_YAML), "-o", str(out)])
    base = yaml.safe_load((ROOT / "examples" / "example_full.yaml").read_text())
    base["header"]["revision"] = "2"
    base_path = tmp_path / "base.yaml"
    base_path.write_text(yaml.safe_dump(base, sort_keys=False))
    r = runner.invoke(
        app,
        [
            "import-openaix",
            str(out / "frago.json"),
            "--base",
            str(base_path),
            "-o",
            str(tmp_path / "x.yaml"),
        ],
    )
    assert r.exit_code == 1
    assert "revision" in r.output


def test_opord_class_is_what_the_frago_base_loads(loaded):
    assert isinstance(loaded[1], OPORD)
