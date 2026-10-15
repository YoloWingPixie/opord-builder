"""Phase 3: OPORD <-> OpenAIX."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from opord_builder.cli import app
from opord_builder.openaix import convert as c
from opord_builder.openaix.from_openaix import OpenAIXImportError, from_openaix
from opord_builder.openaix.registry import VENDOR_DIR, schemas
from opord_builder.openaix.to_openaix import OWNED_PATHS, to_openaix
from opord_builder.openaix.validate import validate
from opord_builder.renderer import load_opord
from opord_builder.schema.core import OPORD

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
MAXIMAL = VENDOR_DIR / "examples" / "maximal"
runner = CliRunner()


def canon(doc) -> str:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _is_opord(path: Path) -> bool:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return False
    return (
        isinstance(data, dict)
        and ("header" in data or data.get("kind") == "opord")
        and "mission" in data
        and "document_kind" not in path.read_text(encoding="utf-8")
    )


def opord_files() -> list[Path]:
    files = [p for p in sorted(EXAMPLES.glob("*.yaml")) if _is_opord(p)]
    files += [
        p
        for p in sorted((EXAMPLES / "operation-steel-opera").glob("*.yaml"))
        if _is_opord(p)
    ]
    return files


def mini(**changes) -> OPORD:
    base = load_opord(EXAMPLES / "example_minimal.yaml")
    data = base.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    for path, value in changes.items():
        node = data
        keys = path.split("__")
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value
    return OPORD.model_validate(data)


# --------------------------------------------------------------------------- acceptance (a)


@pytest.mark.parametrize("path", opord_files(), ids=lambda p: p.name)
def test_yaml_to_openaix_to_yaml_equals_original(path):
    model = load_opord(path)
    bundle = to_openaix(model)  # validates against the vendored schema
    back, _ = from_openaix(bundle.opord, bundle.resources, bundle.jiptl, carry=False)
    assert back == model
    assert validate(bundle.opord) == []
    if bundle.resources:
        assert validate(bundle.resources) == []
    if bundle.jiptl:
        assert validate(bundle.jiptl) == []


def test_required_examples_are_covered():
    names = {p.name for p in opord_files()}
    assert {"example_full.yaml", "example_minimal.yaml"} <= names


def test_steel_opera_has_no_opord_only_spins():
    """The Steel Opera folder holds the SPINS publication only; there is no OPORD to round trip."""
    steel = EXAMPLES / "operation-steel-opera"
    assert (steel / "spins.yaml").exists()
    assert not any(p.parent == steel for p in opord_files())


def test_yaml_text_round_trip_through_cli(tmp_path):
    out = tmp_path / "out"
    r = runner.invoke(
        app, ["export-openaix", str(EXAMPLES / "example_full.yaml"), "-o", str(out)]
    )
    assert r.exit_code == 0, r.output
    assert (out / "opord.json").exists() and (out / "resources.json").exists()
    assert (out / "jiptl.json").exists()
    r = runner.invoke(
        app,
        [
            "validate-openaix",
            str(out / "opord.json"),
            str(out / "resources.json"),
            str(out / "jiptl.json"),
        ],
    )
    assert r.exit_code == 0, r.output
    yml = tmp_path / "back.yaml"
    r = runner.invoke(app, ["import-openaix", str(out / "opord.json"), "-o", str(yml)])
    assert r.exit_code == 0, r.output
    original = load_opord(EXAMPLES / "example_full.yaml")
    back = load_opord(yml)
    assert back.model_copy(update={"openaix_source": None}) == original
    # and the second export is byte for byte the first one (carry-through)
    out2 = tmp_path / "out2"
    r = runner.invoke(app, ["export-openaix", str(yml), "-o", str(out2)])
    assert r.exit_code == 0, r.output
    for name in ("opord.json", "resources.json", "jiptl.json"):
        assert (out / name).read_text() == (out2 / name).read_text()


# --------------------------------------------------------------------------- acceptance (b): carry-through


@pytest.mark.parametrize("with_resources", [False, True])
def test_maximal_opord_round_trip_is_byte_identical(with_resources):
    doc = json.loads((MAXIMAL / "opord.json").read_text())
    res = (
        json.loads((MAXIMAL / "resources.json").read_text()) if with_resources else None
    )
    model, _ = from_openaix(doc, res)
    # through YAML text, as the CLI does
    model = OPORD.model_validate(
        yaml.safe_load(
            yaml.safe_dump(
                model.model_dump(mode="json", exclude_none=True), sort_keys=False
            )
        )
    )
    bundle = to_openaix(model)
    assert canon(bundle.opord) == canon(doc)
    if with_resources:
        assert canon(bundle.resources) == canon(res)


def test_owned_paths_write_over_the_carried_document():
    doc = json.loads((MAXIMAL / "opord.json").read_text())
    model, _ = from_openaix(doc)
    assert doc["situation"]["enemy_forces"]["units"], (
        "fixture must have typed enemy units"
    )
    model = OPORD.model_validate(
        {
            **model.model_dump(mode="json", exclude_none=True),
            "mission": "A new mission statement.",
        }
    )
    out = to_openaix(model).opord
    assert out["mission"]["statement"] == "A new mission statement."
    assert (
        out["situation"]["enemy_forces"]["units"]
        == doc["situation"]["enemy_forces"]["units"]
    )
    assert (
        out["execution"]["tasks_to_subordinate_units"]
        == doc["execution"]["tasks_to_subordinate_units"]
    )
    # untouched owned fields keep their carried bytes
    assert out["meta"] == doc["meta"]
    assert out["extensions"] == doc["extensions"]


def test_owned_paths_are_json_pointers():
    assert all(p.startswith("/") for p in OWNED_PATHS)
    assert len(OWNED_PATHS) == len(set(OWNED_PATHS))


def test_import_rejects_invalid_and_wrong_kind():
    doc = json.loads((MAXIMAL / "opord.json").read_text())
    bad = copy.deepcopy(doc)
    bad["mission"] = {"statement": ""}
    with pytest.raises(OpenAIXImportError, match="mission"):
        from_openaix(bad)
    with pytest.raises(OpenAIXImportError, match="kind"):
        from_openaix({"kind": "ato"})


# --------------------------------------------------------------------------- header, print extension, enums


def test_header_and_print_extension():
    model = load_opord(EXAMPLES / "example_full.yaml")
    doc = to_openaix(model).opord
    assert doc["date_time"] == "2026-04-18T12:00:00Z"
    assert doc["time_zone"] == "Z"
    assert doc["meta"]["classification"] == "UNCLASSIFIED"
    assert doc["order_number"] == model.header.operation_order_number
    print_ext = doc["extensions"]["org.opord-builder.print"]
    for key in (
        "logo",
        "page_icon",
        "watermark",
        "copy_number",
        "number_of_copies",
        "place_of_issue",
        "message_reference_number",
    ):
        assert key in print_ext, key
    assert print_ext["copy_number"] == 3
    # The print extension is closed in 0.2: annex status rides in the authoring extension.
    assert "annex_status" not in print_ext
    status = doc["extensions"]["org.opord-builder.authoring"]["@annex_status"]
    assert set(status.values()) <= {"published", "omitted", "not_used"}
    assert status["A"] == "published"


def test_dtg_round_trip_and_unconvertible_dtg_stays_in_overlay():
    model = mini(header__dtg="311545ZDEC26")
    bundle = to_openaix(model)
    assert bundle.opord["date_time"] == "2026-12-31T15:45:00Z"
    assert from_openaix(bundle.opord, carry=False)[0] == model
    full = load_opord(EXAMPLES / "example_full.yaml")
    b = to_openaix(full)
    assert any("effective_time" in w for w in b.warnings)
    assert "effective_time" not in b.opord["execution"]["coordinating_instructions"]


def test_relationship_enum_uses_table_and_upper_case_survives():
    model = load_opord(EXAMPLES / "example_full.yaml")
    bundle = to_openaix(model)
    doc, res = bundle.opord, bundle.resources
    rels = {r["relationship"] for r in doc["annexes"]["A"]["relationships"]}
    assert {"assigned", "operational_control", "direct_support"} <= rels
    assert (
        from_openaix(doc, res, bundle.jiptl, carry=False)[0] == model
    )  # ASSIGNED / OPCON / DS come back upper-case


# --------------------------------------------------------------------------- task organization


def test_task_organization_is_dfs_with_parents_and_key_order():
    model = mini(
        header__task_organization={
            "name": "TF A",
            "subordinate_units": [
                {
                    "name": "Co B",
                    "relationship": "OPCON",
                    "subordinate_units": [{"name": "Plt B1"}, {"name": "Plt B2"}],
                },
                {"name": "Co C", "subordinate_units": [{"name": "Plt C1"}]},
                {"name": "Co D"},
            ],
        }
    )
    doc = to_openaix(model).opord
    # JSON object key order carries the sibling order: depth first, siblings in authored order
    raw = json.loads(json.dumps(doc))
    assert list(raw["task_organization"]) == [
        "tf-a",
        "co-b",
        "plt-b1",
        "plt-b2",
        "co-c",
        "plt-c1",
        "co-d",
    ]
    t = raw["task_organization"]
    assert "parent" not in t["tf-a"]
    assert t["plt-b2"]["parent"] == "co-b" and t["co-d"]["parent"] == "tf-a"
    assert from_openaix(doc, carry=False)[0] == model


def test_task_organization_collision_suffix():
    model = mini(
        header__task_organization={
            "name": "TF A",
            "subordinate_units": [{"name": "1st Plt"}, {"name": "1st plt"}],
        }
    )
    doc = to_openaix(model).opord
    assert list(doc["task_organization"]) == ["tf-a", "x-1st-plt", "x-1st-plt-2"]
    assert from_openaix(doc, carry=False)[0] == model


# --------------------------------------------------------------------------- annexes


def test_annexes_by_letter_with_status_in_authoring_extension():
    model = mini(
        annexes=[
            {"letter": "B", "body": "Intel body."},
            {"letter": "G"},
            {"letter": "I"},
            {"letter": "Z", "body": "Distro."},
        ]
    )
    doc = to_openaix(model).opord
    assert list(doc["annexes"]) == ["B", "Z"]
    assert doc["annexes"]["B"]["summary"] == "Intel body."
    assert "annex_status" not in doc["extensions"]["org.opord-builder.print"]
    status = doc["extensions"]["org.opord-builder.authoring"]["@annex_status"]
    assert status == {
        "B": "published",
        "G": "omitted",
        "I": "not_used",
        "Z": "published",
    }
    assert from_openaix(doc, carry=False)[0] == model


def test_unsorted_annexes_keep_their_order():
    model = mini(annexes=[{"letter": "C", "body": "c"}, {"letter": "A", "body": "a"}])
    bundle = to_openaix(model)
    assert list(bundle.opord["annexes"]) == ["C", "A"]
    assert from_openaix(bundle.opord, carry=False)[0] == model


def test_annex_with_custom_title_round_trips():
    model = mini(annexes=[{"letter": "C", "title": "Ops (custom)", "body": "x"}])
    doc = to_openaix(model).opord
    assert from_openaix(doc, carry=False)[0].annexes[0].title == "Ops (custom)"


# --------------------------------------------------------------------------- control measures


def _annex_c(items=None, zones=None, fscm=None):
    out = [{"letter": "C", "typed_body": {"letter": "C"}}]
    if items:
        out[0]["typed_body"]["control_measures"] = items
    if zones:
        out[0]["typed_body"]["airspace_control"] = zones
    if fscm:
        out.append(
            {
                "letter": "D",
                "typed_body": {
                    "letter": "D",
                    "fire_support_coordination_measures": fscm,
                },
            }
        )
    return out


def test_measures_use_catalogue_codes_and_extensions():
    grid2 = "32UPU1234512345 32UPU2234512345"
    area = "32UPU1000010000 32UPU1000020000 32UPU2000020000"
    model = mini(
        annexes=_annex_c(
            items=[
                {
                    "name": "PL DAGGER",
                    "type": "phase_line",
                    "grid_or_trace": grid2,
                    "purpose": "Control.",
                },
                {
                    "name": "AXIS ONE",
                    "type": "axis",
                    "grid_or_trace": area,
                    "purpose": "Axis of advance.",
                },
                {
                    "name": "AXIS LINE",
                    "type": "axis",
                    "grid_or_trace": grid2,
                    "purpose": "A trace is not an area.",
                },
                {
                    "name": "OBJ SWORD",
                    "type": "objective",
                    "grid_or_trace": area,
                    "purpose": "Seize.",
                },
            ],
            fscm=[
                {
                    "type": "RFZ",
                    "name": "RFZ ONE",
                    "effective_dtg_start": "181200ZAPR26",
                    "grid_or_coords": area,
                    "remarks": "No fires without approval.",
                },
                {
                    "type": "CFZ",
                    "name": "CFZ ONE",
                    "effective_dtg_start": "181200ZAPR26",
                    "grid_or_coords": area,
                },
                {
                    "type": "SFA",
                    "name": "SFA ONE",
                    "effective_dtg_start": "181200ZAPR26",
                    "grid_or_coords": area,
                },
                {
                    "type": "CFL",
                    "name": "CFL ONE",
                    "effective_dtg_start": "181200ZAPR26",
                    "effective_dtg_end": "181800ZAPR26",
                    "grid_or_coords": grid2,
                },
            ],
            zones={
                "airspace_zones": [
                    {
                        "name": "SAR NORTH",
                        "kind": "SAR",
                        "anchor_point": "32UPU1000010000",
                        "radius_nm": 5.0,
                        "altitude_floor_ft": 0,
                        "altitude_ceiling_ft": 5000,
                        "purpose": "Rescue.",
                    },
                    {
                        "name": "ROZ HAMMER",
                        "kind": "ROZ",
                        "anchor_point": "32UPU1000010000",
                        "radius_nm": 5.0,
                        "altitude_floor_ft": 5000,
                        "altitude_ceiling_ft": 15000,
                        "purpose": "CAS stack.",
                    },
                ],
            },
        )
    )
    bundle = to_openaix(model)
    cm = bundle.resources["resources"]["control_measures"]
    by_name = {v["name"]: v for v in cm.values()}
    assert by_name["PL DAGGER"]["type"] == "PL"
    assert by_name["OBJ SWORD"]["type"] == "OBJ"
    # AXIS and CFZ are catalogue codes since 0.2.0-draft.1
    assert by_name["AXIS ONE"]["type"] == "AXIS"
    assert by_name["AXIS ONE"]["geometry"]["kind"] == "polygon"
    assert by_name["AXIS LINE"]["type"] == c.MEASURE_NAMESPACE  # a trace is no area
    assert by_name["AXIS LINE"]["extensions"][c.MEASURE_NAMESPACE]["code"] == "AXIS"
    assert by_name["CFZ ONE"]["type"] == "CFZ"
    assert by_name["RFZ ONE"]["type"] == "RFA"  # RFZ -> RFA
    assert by_name["RFZ ONE"]["restrictions"] == ["No fires without approval."]
    assert by_name["SFA ONE"]["type"] == c.MEASURE_NAMESPACE
    assert by_name["SFA ONE"]["extensions"][c.MEASURE_NAMESPACE]["code"] == "SFA"
    assert by_name["CFL ONE"]["type"] == "CFL"
    # SAR is the catalogue's Search and Rescue Point: a POINT with the search_and_rescue role
    sar = by_name["SAR NORTH"]
    assert (sar["type"], sar["roles"]) == ("POINT", ["search_and_rescue"])
    assert sar["altitude"]["upper"]["value"] == 5000 and "position" in sar
    assert c.MEASURE_NAMESPACE not in sar.get("extensions", {})
    assert by_name["ROZ HAMMER"]["type"] == "ROZ"
    assert by_name["ROZ HAMMER"]["components"][0]["geometry"]["kind"] == "circle"
    # the OPORD names them by identifier
    c_annex = bundle.opord["annexes"]["C"]
    assert c_annex["operation_overlay"] == [
        "pl-dagger",
        "axis-one",
        "axis-line",
        "obj-sword",
    ]
    assert c_annex["airspace"]["measures"] == ["sar-north", "roz-hammer"]
    assert bundle.opord["annexes"]["D"]["fire_support_coordination_measures"] == [
        "rfz-one",
        "cfz-one",
        "sfa-one",
        "cfl-one",
    ]
    assert bundle.opord["resources_ref"]["id"] == bundle.resources["meta"]["id"]
    # lossless
    assert (
        from_openaix(bundle.opord, bundle.resources, bundle.jiptl, carry=False)[0]
        == model
    )


def test_frequency_table_rows_become_channels():
    model = mini(
        annexes=[
            {
                "letter": "H",
                "appendices": [
                    {
                        "number": 1,
                        "title": "Comms",
                        "frequency_tables": [
                            {
                                "title": "Nets",
                                "channels": [
                                    {
                                        "name": "CAS Primary",
                                        "channel": "Ch 3",
                                        "frequency": "251.0 AM",
                                        "purpose": "CAS",
                                    },
                                    {
                                        "name": "Guard",
                                        "channel": "Ch 1",
                                        "frequency": "243.000 MHz AM",
                                        "purpose": "Guard",
                                    },
                                    {
                                        "name": "Satcom",
                                        "channel": "SAT 1",
                                        "frequency": "SAT-1",
                                        "purpose": "Reachback",
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    )
    bundle = to_openaix(model)
    ch = bundle.resources["resources"]["channels"]
    assert set(ch) == {
        "cas-primary",
        "guard",
    }  # SAT-1 is not a frequency: stays in the overlay
    assert ch["cas-primary"]["frequency"] == {
        "value": 251.0,
        "unit": "MHz",
        "modulation": "AM",
        "band": "uhf",
    }
    assert (
        from_openaix(bundle.opord, bundle.resources, bundle.jiptl, carry=False)[0]
        == model
    )


def test_import_skips_measures_the_model_cannot_hold():
    doc = json.loads((MAXIMAL / "opord.json").read_text())
    res = json.loads((MAXIMAL / "resources.json").read_text())
    model, warns = from_openaix(doc, res)
    assert any("not imported" in w or "not in the resources" in w for w in warns)
    assert model.annexes  # the rest still imports


# --------------------------------------------------------------------------- Annex D targeting


def test_example_full_targeting_is_typed():
    model = load_opord(EXAMPLES / "example_full.yaml")
    b = to_openaix(model)
    assert b.jiptl["kind"] == "jiptl" and validate(b.jiptl) == []
    first = b.jiptl["targets"][0]
    assert first["target_number"] == "TGT 0042" and first["priority_rank"] == 1
    assert (
        first["desired_effect"] == "neutralize"
        and first["location_mgrs"] == "32UMA123456"
    )
    assert first["authorized_engagement_means"][0] == {
        "system": "M777 DS Btry (B/4-319)"
    }
    assert "category" not in first  # no OpenAIX field at draft.2: authoring overlay
    tsts = b.opord["annexes"]["D"]["targeting"]["time_sensitive_targets"]
    assert [t["tst_number"] for t in tsts] == ["TST-01", "TST-02", "TST-03"]
    assert tsts[0]["priority"] == 1
    assert tsts[0]["target"] in b.resources["resources"]["targets"]
    assert from_openaix(b.opord, b.resources, b.jiptl, carry=False)[0] == model


def test_hpt_is_typed_with_the_attack_guidance_rows():
    hvt = {
        "priority_rank": 1,
        "category": "C2",
        "target_description": "ENY CP",
        "signature": "antennas",
        "engagement_guidance": "Neutralize.",
        "hpt_nomination": True,
    }
    row = {
        "hpt_reference": "HPT #1",
        "when": "Planned",
        "how": "Arty",
        "effect": "Neutralize",
    }
    model = mini(
        annexes=[
            {
                "letter": "D",
                "typed_body": {
                    "letter": "D",
                    "high_payoff_target_list": [hvt],
                    "attack_guidance_matrix": [row],
                },
            }
        ]
    )
    b = to_openaix(model)
    hpt = b.opord["annexes"]["D"]["targeting"]["high_payoff_targets"]
    assert (
        hpt[0]["effect"] == "neutralize"
        and hpt[0]["timing"] == "planned"
        and hpt[0]["priority"] == 1
    )
    assert b.resources["resources"]["targets"][hpt[0]["target"]]["name"] == "ENY CP"
    assert from_openaix(b.opord, b.resources, b.jiptl, carry=False)[0] == model
    # an effect OpenAIX has no value for keeps the pair in the authoring overlay
    model2 = mini(
        annexes=[
            {
                "letter": "D",
                "typed_body": {
                    "letter": "D",
                    "high_payoff_target_list": [hvt],
                    "attack_guidance_matrix": [{**row, "effect": "Harass"}],
                },
            }
        ]
    )
    b2 = to_openaix(model2)
    assert "targeting" not in b2.opord.get("annexes", {}).get("D", {})
    assert from_openaix(b2.opord, b2.resources, b2.jiptl, carry=False)[0] == model2


def test_jpitl_without_its_document_imports_without_the_list():
    model = load_opord(EXAMPLES / "example_full.yaml")
    b = to_openaix(model)
    back, warns = from_openaix(b.opord, b.resources, None, carry=False)
    d = next(a for a in back.annexes if a.letter == "D").typed_body
    assert d.jpitl == [] and any("dropped" in w for w in warns)


def test_retired_target_documents_are_gone():
    from opord_builder.schema.data_sources import DATA_SOURCE_REGISTRY

    for kind in ("jpitl", "tst", "hpt"):
        assert kind not in DATA_SOURCE_REGISTRY
        assert not (ROOT / "schemas" / f"{kind}.schema.json").exists()
    assert not (EXAMPLES / "data_sources" / "fires").exists()


# --------------------------------------------------------------------------- 0.2 gameplay fields


def _nine_line(**changes):
    line = {
        "ip_or_bp": "IP ALPHA",
        "heading_magnetic": 88,
        "heading_offset": "L",
        "distance_nm": 15.0,
        "target_elevation_ft": 1740,
        "target_description": "2x T-72 in a tree line",
        "target_location": "32UMA1245645456",
        "mark_type": "IR_POINTER",
        "laser_code": "1688",
        "friendlies_distance_m": 850,
        "friendlies_direction": "SW",
        "friendlies_marking": "ir strobe",
        "egress": "SOUTH LOW",
        "final_attack_heading": 90,
        "time_on_target": "190500ZAPR26",
        "time_to_target_min": 12,
        "type_of_control": "TYPE_2",
        "control_agency": "DAGGER 11",
        "cas_callsign": "VIPER 11",
        "threats": ["SA-13", "MANPADS"],
        "hazards": ["Wires on the final"],
        "danger_close": True,
        "ground_commander_initials": "T.M.",
        "remarks": "Abort code THUNDER.",
    }
    line.update(changes)
    return line


def _cas_model(*lines):
    return mini(
        annexes=[
            {
                "letter": "D",
                "typed_body": {"letter": "D", "cas_nine_lines": list(lines)},
            }
        ]
    )


def test_nine_line_cas_is_typed_as_a_cas_brief():
    model = _cas_model(_nine_line())
    bundle = to_openaix(model)
    (brief,) = bundle.opord["annexes"]["D"]["air_support"]["cas_briefs"]
    assert brief["id"] == "cas-1"
    assert brief["heading"] == {"value": 88, "reference": "magnetic"}
    assert brief["offset_direction"] == "left"
    assert brief["distance"] == {"value": 15.0, "unit": "nm"}
    assert brief["target_elevation"] == {
        "value": 1740,
        "reference": "MSL",
        "unit": "ft",
    }
    assert brief["mark"] == "infrared_pointer"  # was `infrared` before 0.2
    assert brief["laser_code"] == "1688"
    assert brief["friendly_distance"] == {"value": 850, "unit": "m"}
    assert brief["friendly_direction"] == "south_west"
    assert brief["friendly_marking"] == "infrared_strobe"
    assert brief["final_attack_headings"] == [
        {
            "start_bearing": {"value": 90, "reference": "magnetic"},
            "end_bearing": {"value": 90, "reference": "magnetic"},
        }
    ]
    assert brief["time_on_target"] == "2026-04-19T05:00:00Z"
    assert brief["time_to_target_seconds"] == 720
    assert brief["control_type"] == "type_2"
    assert brief["danger_close"] is True
    assert brief["remarks"] == "Abort code THUNDER."
    assert brief["hazards"] == [{"kind": "other", "description": "Wires on the final"}]
    threats = bundle.resources["resources"]["threats"]
    assert [threats[t]["name"] for t in brief["threats"]] == ["SA-13", "MANPADS"]
    assert validate(bundle.opord) == [] and validate(bundle.resources) == []
    # what has no typed home stays in the authoring overlay; the rest does not
    stash = bundle.opord["extensions"]["org.opord-builder.authoring"]["annexes.0"]
    prefix = "annexes.0.typed_body.cas_nine_lines.0."
    assert {k.removeprefix(prefix) for k in stash if k.startswith(prefix)} == {
        "ip_or_bp",
        "egress",
        "control_agency",
        "cas_callsign",
        "ground_commander_initials",
    }
    assert from_openaix(bundle.opord, bundle.resources, carry=False)[0] == model


@pytest.mark.parametrize("mark", ["NONE", "GOGGLES"])
def test_cas_mark_without_an_openaix_value_is_left_out_and_survives(mark):
    model = _cas_model(_nine_line(mark_type=mark, laser_code=None))
    bundle = to_openaix(model)
    (brief,) = bundle.opord["annexes"]["D"]["air_support"]["cas_briefs"]
    assert "mark" not in brief  # no `none` value: absent means no mark
    stash = bundle.opord["extensions"]["org.opord-builder.authoring"]["annexes.0"]
    assert stash["annexes.0.typed_body.cas_nine_lines.0.mark_type"] == mark
    assert from_openaix(bundle.opord, bundle.resources, carry=False)[0] == model


def test_cas_values_that_do_not_fit_stay_in_the_overlay():
    line = _nine_line(
        laser_code="1999",
        friendlies_marking="red smoke and a panel",
        friendlies_direction="NNE",
    )
    model = _cas_model(line)
    bundle = to_openaix(model)
    (brief,) = bundle.opord["annexes"]["D"]["air_support"]["cas_briefs"]
    assert not {"laser_code", "friendly_marking", "friendly_direction"} & set(brief)
    assert validate(bundle.opord) == []
    assert from_openaix(bundle.opord, bundle.resources, carry=False)[0] == model


def test_cas_without_an_mgrs_location_stays_whole_in_the_overlay():
    model = _cas_model(_nine_line(), _nine_line(target_location="the bridge"))
    bundle = to_openaix(model)
    assert "air_support" not in bundle.opord.get("annexes", {}).get("D", {})
    assert from_openaix(bundle.opord, bundle.resources, carry=False)[0] == model


def test_cas_threats_are_shared_between_briefs():
    model = _cas_model(_nine_line(), _nine_line(target_location="32UMA1300045456"))
    bundle = to_openaix(model)
    briefs = bundle.opord["annexes"]["D"]["air_support"]["cas_briefs"]
    assert briefs[0]["threats"] == briefs[1]["threats"]
    assert len(bundle.resources["resources"]["threats"]) == 2
    assert from_openaix(bundle.opord, bundle.resources, carry=False)[0] == model


def test_cas_brief_from_openaix_reads_the_new_fields():
    doc = json.loads((MAXIMAL / "opord.json").read_text())
    res = json.loads((MAXIMAL / "resources.json").read_text())
    model, warns = from_openaix(doc, res, carry=False)
    briefs = doc["annexes"]["D"]["air_support"]["cas_briefs"]
    # the example briefs lack the fields the authoring model requires (IP, egress): skipped with a warning
    assert briefs and any("cas_nine_lines" in w for w in warns)
    d = next(a for a in model.annexes if a.letter == "D")
    assert not getattr(d.typed_body, "cas_nine_lines", [])


def test_jpitl_enums_are_lower_case_in_openaix():
    model = load_opord(EXAMPLES / "example_full.yaml")
    b = to_openaix(model)
    for t in b.jiptl["targets"]:
        assert t["status"] == t["status"].lower()
        assert t["desired_effect"] == t["desired_effect"].lower()
        assert t.get("component_tasked", "x") == t.get("component_tasked", "x").lower()
    back, _ = from_openaix(b.opord, b.resources, b.jiptl, carry=False)
    assert back == model
    original = [
        e.status for a in model.annexes if a.letter == "D" for e in a.typed_body.jpitl
    ]
    assert original and all(s.isupper() for s in original)  # authoring keeps upper case


def test_jpitl_component_io_has_no_openaix_value_and_stays_in_the_overlay():
    model = load_opord(EXAMPLES / "example_full.yaml")
    data = model.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    d = next(a for a in data["annexes"] if a["letter"] == "D")
    d["typed_body"]["jpitl"][0]["component_tasked"] = "IO"
    model = OPORD.model_validate(data)
    b = to_openaix(model)
    assert "component_tasked" not in b.jiptl["targets"][0]
    assert validate(b.jiptl) == []
    assert from_openaix(b.opord, b.resources, b.jiptl, carry=False)[0] == model


def test_classification_caveat_is_typed_in_the_closed_print_extension():
    model = mini(header__classification_caveat="REL TO USA, FVEY")
    doc = to_openaix(model).opord
    ext = doc["extensions"]["org.opord-builder.print"]
    assert ext["classification_caveat"] == "REL TO USA, FVEY"
    allowed = set(schemas()["opord"]["$defs"]["PrintExtension"]["properties"])
    assert set(ext) <= allowed  # the extension is closed in 0.2
    assert from_openaix(doc, carry=False)[0] == model


def test_sar_zone_is_the_catalogue_sardot_point():
    zone = {
        "name": "SAR NORTH",
        "kind": "SAR",
        "anchor_point": "32UPU1000010000",
        "radius_nm": 5.0,
        "altitude_floor_ft": 0,
        "altitude_ceiling_ft": 5000,
        "purpose": "Rescue.",
    }
    model = _zones_model(zone)
    bundle = to_openaix(model)
    doc = next(iter(bundle.resources["resources"]["control_measures"].values()))
    assert doc["type"] == "POINT" and doc["roles"] == ["search_and_rescue"]
    assert doc["altitude"] == {
        "lower": {"value": 0, "unit": "ft", "reference": "MSL"},
        "upper": {"value": 5000, "unit": "ft", "reference": "MSL"},
    }
    assert doc["description"] == "Rescue."
    assert c.MEASURE_NAMESPACE not in doc.get("extensions", {})
    # the radius has no field on a point: it rides in the authoring overlay
    stash = bundle.opord["extensions"]["org.opord-builder.authoring"]["annexes.0"]
    assert (
        stash["annexes.0.typed_body.airspace_control.airspace_zones.0.radius_nm"] == 5.0
    )
    assert from_openaix(bundle.opord, bundle.resources, carry=False)[0] == model


def test_sar_zone_without_an_anchor_point_stays_an_extension_measure():
    zone = {
        "name": "SAR CORRIDOR",
        "kind": "SAR",
        "polygon_vertices": ["32UPU1000010000", "32UPU1000020000", "32UPU2000020000"],
        "altitude_floor_ft": 0,
        "altitude_ceiling_ft": 5000,
        "purpose": "Rescue.",
    }
    model = _zones_model(zone)
    bundle = to_openaix(model)
    doc = next(iter(bundle.resources["resources"]["control_measures"].values()))
    assert doc["type"] == c.MEASURE_NAMESPACE
    assert doc["extensions"][c.MEASURE_NAMESPACE]["code"] == "SARDOT"
    assert from_openaix(bundle.opord, bundle.resources, carry=False)[0] == model


def _zones_model(*zones):
    return mini(
        annexes=[
            {
                "letter": "C",
                "typed_body": {
                    "letter": "C",
                    "airspace_control": {"airspace_zones": list(zones)},
                },
            }
        ]
    )


def test_anchor_georef_uses_the_anchor_point_role():
    ref = {"name": "ANCHOR ONE", "kind": "ANCHOR", "coordinates": "32UPU1000010000"}
    model = mini(
        annexes=[
            {
                "letter": "C",
                "typed_body": {"letter": "C", "airspace_control": {"geo_refs": [ref]}},
            }
        ]
    )
    bundle = to_openaix(model)
    doc = next(iter(bundle.resources["resources"]["control_measures"].values()))
    assert doc["roles"] == ["anchor"]
    assert from_openaix(bundle.opord, bundle.resources, carry=False)[0] == model
