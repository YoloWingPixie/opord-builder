"""Kneeboards from an OpenAIX ATO (phase 2): fixture, cards, merge, CLI, golden HTML."""

from __future__ import annotations

import copy
import json
import os
import struct
from pathlib import Path

import pytest
from typer.testing import CliRunner

from opord_builder import renderer
from opord_builder.cli import app
from opord_builder.openaix.kneeboard import (
    build_cards,
    cards_from_files,
    load_document,
    merge_resources,
    merge_with_yaml,
)
from opord_builder.openaix.validate import validate
from opord_builder.schema.shared import KneeboardCard

FIX = Path(__file__).parent / "fixtures" / "openaix" / "atomic-thunder"
ATO = FIX / "ato.json"
RES = FIX / "resources.json"
GOLDEN = FIX / "viper-1.html"
STAMP = "141200ZOCT26"


@pytest.fixture(scope="module")
def docs():
    ato = json.loads(ATO.read_text())
    res = json.loads(RES.read_text())
    return ato, res, merge_resources(ato, res)


def card_for(docs, flight="viper-1", mutate=None):
    ato, res, _ = copy.deepcopy(docs)
    if mutate:
        mutate(ato, res)
    cards, warns = build_cards(
        ato, merge_resources(ato, {"resources": res["resources"]}), flight
    )
    return cards[0], warns


def viper(ato):
    return ato["missions"][0]["flights"][0]


def has_warning(warns, text):
    return any(text in w for w in warns)


# ----------------------------------------------------------------------- fixture


@pytest.mark.parametrize("path", [ATO, RES])
def test_fixture_validates(path):
    assert validate(json.loads(path.read_text())) == []


def test_fixture_shape(docs):
    ato, _, res = docs
    flights = {f["id"]: f for m in ato["missions"] for f in m["flights"]}
    assert (
        flights["viper-1"]["count"] == 4 and flights["viper-1"]["callsign"] == "Viper 1"
    )
    assert res["aircraft_types"][flights["viper-1"]["aircraft_type"]][
        "name"
    ].startswith("F-16C")
    assert res["places"]["etad"]["ident"] == "ETAD"
    assert ato["missions"][1]["tasking"]["kind"] == "refueling"


def test_load_document_rejects_wrong_kind_and_invalid(tmp_path):
    with pytest.raises(ValueError, match="expected an OpenAIX 'ato'"):
        load_document(RES, "ato")
    bad = tmp_path / "bad.json"
    bad.write_text('{"kind": "ato"}')
    with pytest.raises(ValueError, match="not a valid OpenAIX ato"):
        load_document(bad, "ato")


# ----------------------------------------------------------------- table rows


def test_header_fields(docs):
    c, _ = card_for(docs)
    assert (c.flight_callsign, c.title, c.msn_number) == ("Viper 1", "Viper 1", "4101")


def test_one_card_per_flight(docs):
    ato, _, res = docs
    cards, _ = build_cards(ato, res)
    assert [c.flight_callsign for c in cards] == ["Viper 1", "Shell 1"]


def test_unknown_flight_lists_known_ids(docs):
    ato, _, res = docs
    with pytest.raises(ValueError, match="viper-1, shell-1"):
        build_cards(ato, res, "nope")


def test_positions_count_and_laser_from_scl(docs):
    c, _ = card_for(docs)
    assert [p.number for p in c.positions] == [1, 2, 3, 4]
    assert {p.laser for p in c.positions} == {"1688"}


def test_member_scl_override_changes_laser(docs):
    def mut(ato, res):
        res["resources"]["scls"]["f16-alt"] = {
            **res["resources"]["scls"]["f16-oca"],
            "id": "f16-alt",
            "laser_code": "1511",
        }
        viper(ato)["configuration"]["member_overrides"].append(
            {"member": 3, "scl": "f16-alt"}
        )

    c, _ = card_for(docs, mutate=mut)
    assert [p.laser for p in c.positions] == ["1688", "1688", "1511", "1688"]


def test_tacan_lead_and_flight(docs):
    c, w = card_for(docs)
    assert (c.tacan.lead, c.tacan.flight) == ("14Y", "77Y")

    def mut(ato, res):
        viper(ato)["configuration"].pop("member_overrides")

    c, w = card_for(docs, mutate=mut)
    assert c.tacan.lead == "" and has_warning(w, "tacan.lead")


def test_objectives_and_weaponeering(docs):
    c, _ = card_for(docs)
    assert c.primary_objectives == [
        "Destroy hardened shelters at the fictional airbase"
    ]
    assert c.weaponeering == "Viper OCA (4x GBU-12, 2x AIM-120, 2x AIM-9)"


def test_fuel_plan_lb_and_kg_conversion(docs):
    c, _ = card_for(docs)
    f = c.fuel_plan
    assert (f.joker_lbs, f.bingo_lbs, f.rcv_tank_lbs) == (2800, 1500, 4000)

    def mut(ato, res):
        viper(ato)["fuel"]["joker"] = {"value": 1000, "unit": "kg"}

    c, _ = card_for(docs, mutate=mut)
    assert c.fuel_plan.joker_lbs == 2205


def test_comms_phases_by_radio_and_intra(docs):
    c, _ = card_for(docs)
    (phase,) = c.comms.phases
    assert phase.comm1 == "Overlord control: 251.0 MHz AM (BTN 1)"
    assert phase.comm2 == "Strike common: 133.5 MHz AM (BTN 2)"
    assert c.comms.intra == "276.5 MHz AM"
    assert "Shell" not in phase.comm1  # tanker channel is under tankers[]


def test_mids_from_datalink_fields(docs):
    c, _ = card_for(docs)
    assert c.comms.mids == "Link 16 Net 1 STN 01201"


def test_tankers(docs):
    c, _ = card_for(docs)
    (t,) = c.tankers
    assert (t.callsign, t.frequency, t.tacan, t.button) == (
        "Shell 1",
        "240.1 MHz AM",
        "41Y",
        "BTN 16",
    )


def test_tanker_not_serving_flight_is_excluded(docs):
    def mut(ato, res):
        ato["missions"][1]["tasking"]["receivers"] = [{"flight": "someone-else"}]
        ato["missions"][0].pop("support")

    c, w = card_for(docs, mutate=mut)
    assert c.tankers == [] and has_warning(w, "no Refueling mission")


def test_atc_from_launch_and_recovery_fields(docs):
    c, _ = card_for(docs)
    assert [(a.name, a.frequency) for a in c.atc] == [
        ("ETAD GROUND", "121.8 MHz AM"),
        ("ETAD TOWER", "257.8 MHz AM"),
        ("ETAD APPROACH", "263.0 MHz AM"),
    ]


def test_atc_distinct_recovery_field(docs):
    def mut(ato, res):
        viper(ato)["recovery"]["destination"] = "etar"

    c, _ = card_for(docs, mutate=mut)
    assert c.atc[-1].name == "ETAR TOWER"


# ------------------------------------------------------------------- warnings


def test_branch_fields_blank_with_warnings(docs):
    c, w = card_for(docs)
    assert all(p.modex == "" and p.pers == "" for p in c.positions)
    assert c.fuel_plan.msn_req_lbs == 0 and c.baro_alt == ""
    for field in (
        "positions[].modex",
        "positions[].pers",
        "fuel_plan.msn_req_lbs",
        "comms.phases",
        "baro_alt",
    ):
        assert has_warning(w, f"Viper 1: {field}"), field
    assert not has_warning(w, "comms.mids")  # datalink_* exists at draft.2


def test_missing_sources_warn_and_stay_blank(docs):
    def mut(ato, res):
        f = viper(ato)
        for k in ("fuel", "communications", "identification", "launch", "recovery"):
            f.pop(k)
        res["resources"]["scls"]["f16-oca"].pop("laser_code")
        ato["missions"][0]["tasking"].pop("objective")

    c, w = card_for(docs, mutate=mut)
    assert c.comms.intra == "" and c.comms.mids == "" and c.comms.phases == []
    assert c.atc == [] and c.primary_objectives == []
    assert c.fuel_plan.joker_lbs == 0 and c.fuel_plan.rcv_tank_lbs == 4000
    assert all(p.laser == "" for p in c.positions)
    for field in (
        "positions[].laser",
        "tacan.flight",
        "primary_objectives",
        "fuel_plan.joker_lbs",
        "comms.intra",
        "comms.mids",
        "atc",
    ):
        assert has_warning(w, f"Viper 1: {field}"), field


# ----------------------------------------------------------------- YAML merge


def yaml_card(**kw):
    return KneeboardCard(flight_callsign="VIPER1", **kw)


def test_yaml_modex_override_wins_field_by_field(docs):
    c, _ = card_for(docs)
    y = yaml_card(positions=[{"number": 1, "modex": "401"}])
    (m,), warns = merge_with_yaml([c], [y])
    assert m.positions[0].modex == "401"
    assert [p.laser for p in m.positions] == ["1688"] * 4  # untouched fields kept
    assert len(m.positions) == 4 and m.flight_callsign == "Viper 1"
    assert warns == []  # ATO modex was blank: filling a blank is not a disagreement


def test_yaml_disagreement_warns(docs):
    c, _ = card_for(docs)
    y = yaml_card(
        positions=[{"number": 1, "laser": "1511"}],
        tacan={"lead": "99Y"},
        weaponeering="Different load",
    )
    (m,), warns = merge_with_yaml([c], [y])
    assert (m.positions[0].laser, m.tacan.lead, m.tacan.flight) == (
        "1511",
        "99Y",
        "77Y",
    )
    assert m.weaponeering == "Different load"
    assert len(warns) == 3
    assert has_warning(
        warns, "positions[0].laser: YAML value '1511' overrides ATO value '1688'"
    )
    assert has_warning(warns, "tacan.lead") and has_warning(warns, "weaponeering")


def test_yaml_equal_value_is_silent_and_unmatched_cards_are_kept(docs):
    c, _ = card_for(docs)
    other = KneeboardCard(flight_callsign="Hawg 2")
    merged, warns = merge_with_yaml([c], [yaml_card(msn_number="4101"), other])
    assert warns == [] and [m.flight_callsign for m in merged] == ["Viper 1", "Hawg 2"]
    merged, _ = merge_with_yaml([c], [other], keep_unmatched=False)
    assert [m.flight_callsign for m in merged] == ["Viper 1"]


# ------------------------------------------------------------------------ CLI


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_cli_ato_flight_writes_768x1024_png(tmp_path):
    r = CliRunner().invoke(
        app,
        [
            "kneeboard",
            "--ato",
            str(ATO),
            "--flight",
            "viper-1",
            "--resources",
            str(RES),
            "-o",
            str(tmp_path),
        ],
    )
    assert r.exit_code == 0, r.output
    (png,) = tmp_path.glob("*.png")
    assert png_size(png) == (768, 1024)
    assert "warning: Viper 1: baro_alt" in r.output  # warnings go to stderr


def test_cli_without_flight_renders_every_flight(tmp_path):
    r = CliRunner().invoke(
        app,
        ["kneeboard", "--ato", str(ATO), "--resources", str(RES), "-o", str(tmp_path)],
    )
    assert r.exit_code == 0, r.output
    assert len(list(tmp_path.glob("*.png"))) == 2


def test_cli_needs_a_source_and_ato_for_flight(tmp_path):
    runner = CliRunner()
    assert runner.invoke(app, ["kneeboard"]).exit_code == 2
    assert runner.invoke(app, ["kneeboard", "--flight", "viper-1"]).exit_code == 2
    r = runner.invoke(
        app, ["kneeboard", "--ato", str(ATO), "--flight", "nope", "-o", str(tmp_path)]
    )
    assert r.exit_code == 2 and "no flight 'nope'" in r.output


def test_cli_combines_yaml_cards_with_ato(tmp_path):
    base = Path(__file__).parent.parent / "examples" / "example_minimal.yaml"
    yml = tmp_path / "opord.yaml"
    yml.write_text(
        base.read_text(encoding="utf-8")
        + "\nkneeboards:\n  - flight_callsign: VIPER1\n    weaponeering: Other load\n"
        "  - flight_callsign: HAWG2\n",
        encoding="utf-8",
    )
    out = tmp_path / "png"
    r = CliRunner().invoke(
        app,
        [
            "kneeboard",
            str(yml),
            "--ato",
            str(ATO),
            "--resources",
            str(RES),
            "-o",
            str(out),
        ],
    )
    assert r.exit_code == 0, r.output
    assert "weaponeering: YAML value 'Other load' overrides ATO value" in r.output
    assert (
        len(list(out.glob("opord_kneeboard_*.png"))) == 3
    )  # Viper 1 (merged), Shell 1, Hawg 2


# --------------------------------------------------------------- golden HTML


def test_rendered_html_matches_golden(monkeypatch):
    monkeypatch.setattr(renderer, "_now_utc_stamp", lambda: STAMP)
    cards, _ = cards_from_files(ATO, RES, "viper-1")
    html = renderer.render_kneeboard_html(cards[0])
    if os.environ.get(
        "UPDATE_GOLDEN"
    ):  # UPDATE_GOLDEN=1 uv run pytest tests/test_openaix_kneeboard.py
        GOLDEN.write_text(html, encoding="utf-8")
    assert html == GOLDEN.read_text(encoding="utf-8")
