"""Kneeboard cards (dicts) from an OpenAIX ATO: cards, overrides, files, golden HTML."""

from __future__ import annotations

import copy
import json
import os
import struct
from pathlib import Path

import pytest
import yaml

from opord_builder import render
from opord_builder.kneeboard import (
    build_cards,
    cards_from_document,
    cards_from_files,
    merge,
    merge_resources,
    render_card_html,
    render_card_png,
    render_cards,
    validate_cards,
)
from opord_builder.openaix.validate import validate

FIX = Path(__file__).parent / "fixtures" / "openaix" / "atomic-thunder"
ATO = FIX / "ato.json"
RES = FIX / "resources.json"
OPORD = FIX / "opord.json"
GOLDEN = FIX / "viper-1.html"
STAMP = "141200ZOCT26"
EXT = "org.opord-builder.kneeboard"


@pytest.fixture(scope="module")
def docs():
    ato = json.loads(ATO.read_text())
    res = json.loads(RES.read_text())
    return ato, res, merge_resources(ato, res)


def card_for(docs, flight="viper-1", mutate=None, opord=None):
    ato, res, _ = copy.deepcopy(docs)
    if mutate:
        mutate(ato, res)
    cards, warns = build_cards(
        ato, merge_resources(ato, {"resources": res["resources"]}), flight, opord
    )
    return cards[0], warns


def viper(ato):
    return ato["missions"][0]["flights"][0]


def has_warning(warns, text):
    return any(text in w for w in warns)


# ----------------------------------------------------------------------- fixture


@pytest.mark.parametrize("path", [ATO, RES, OPORD])
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


# ----------------------------------------------------------------------- table rows


def test_header_fields(docs):
    c, _ = card_for(docs)
    assert (c["flight_callsign"], c["title"], c["msn_number"]) == (
        "Viper 1",
        "Viper 1",
        "4101",
    )


def test_one_card_per_flight(docs):
    ato, _, res = docs
    cards, _ = build_cards(ato, res)
    assert [c["flight_callsign"] for c in cards] == ["Viper 1", "Shell 1"]


def test_unknown_flight_lists_known_ids(docs):
    ato, _, res = docs
    with pytest.raises(ValueError, match="viper-1, shell-1"):
        build_cards(ato, res, "nope")


def test_positions_count_and_laser_from_scl(docs):
    c, _ = card_for(docs)
    assert [p["number"] for p in c["positions"]] == [1, 2, 3, 4]
    # member 2 has its own laser_code; the others take the SCL's
    assert [p["laser"] for p in c["positions"]] == ["1688", "1687", "1688", "1688"]


def test_aircraft_laser_code_beats_the_scl(docs):
    def mut(ato, res):
        for o in viper(ato)["configuration"]["member_overrides"]:
            o.pop("laser_code", None)

    c, _ = card_for(docs, mutate=mut)
    assert {p["laser"] for p in c["positions"]} == {"1688"}


def test_board_number_and_crew_fill_modex_and_pers(docs):
    c, w = card_for(docs)
    assert [(p["modex"], p["pers"]) for p in c["positions"]] == [
        ("401", "Maverick"),
        ("402", "Goose"),
        ("403", "Iceman"),
        ("404", "Viper / Jester"),  # a two-seater lists its crew in seat order
    ]
    assert not has_warning(w, "positions[].modex")
    assert not has_warning(w, "positions[].pers")

    def mut(ato, res):
        for o in viper(ato)["configuration"]["member_overrides"]:
            o.pop("board_number", None)
            o.pop("crew", None)

    c, w = card_for(docs, mutate=mut)
    assert all(p["modex"] == "" and p["pers"] == "" for p in c["positions"])
    assert has_warning(w, "Viper 1: positions[].modex")
    assert has_warning(w, "Viper 1: positions[].pers")


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
    assert [p["laser"] for p in c["positions"]] == ["1688", "1687", "1511", "1688"]


def test_tacan_lead_and_flight(docs):
    c, w = card_for(docs)
    assert (c["tacan"]["lead"], c["tacan"]["flight"]) == ("14Y", "77Y")

    def mut(ato, res):
        viper(ato)["configuration"].pop("member_overrides")

    c, w = card_for(docs, mutate=mut)
    assert c["tacan"]["lead"] == "" and has_warning(w, "tacan.lead")


def test_objectives_and_weaponeering(docs):
    c, _ = card_for(docs)
    assert c["primary_objectives"] == [
        "Destroy hardened shelters at the fictional airbase"
    ]
    assert c["weaponeering"] == "Viper OCA (4x GBU-12, 2x AIM-120, 2x AIM-9)"


def test_fuel_plan_lb_and_kg_conversion(docs):
    c, w = card_for(docs)
    f = c["fuel_plan"]
    assert (f["msn_req_lbs"], f["joker_lbs"], f["bingo_lbs"], f["rcv_tank_lbs"]) == (
        5200,
        2800,
        1500,
        4000,
    )
    assert not has_warning(w, "fuel_plan.msn_req_lbs")

    def no_req(ato, res):
        viper(ato)["fuel"].pop("mission_required")

    c, w = card_for(docs, mutate=no_req)
    assert c["fuel_plan"]["msn_req_lbs"] == 0 and has_warning(
        w, "fuel_plan.msn_req_lbs"
    )

    def mut(ato, res):
        viper(ato)["fuel"]["joker"] = {"value": 1000, "unit": "kg"}

    c, _ = card_for(docs, mutate=mut)
    assert c["fuel_plan"]["joker_lbs"] == 2205

    def req_kg(ato, res):
        viper(ato)["fuel"]["mission_required"] = {"value": 2000, "unit": "kg"}

    c, _ = card_for(docs, mutate=req_kg)
    assert c["fuel_plan"]["msn_req_lbs"] == 4409


def test_comms_phases_grouped_by_activities(docs):
    c, w = card_for(docs)
    rows = [(p["phase"], p["comm1"], p["comm2"]) for p in c["comms"]["phases"]]
    assert rows == [
        # no `activities`: the complete mission
        ("ALL PHASES", "Overlord control: 251.0 MHz AM (BTN 1)", ""),
        ("DEPARTURE", "", "Spang Ground: 121.8 MHz AM (BTN 3)"),
        ("PUSH", "", "Strike common: 133.5 MHz AM (BTN 2)"),
        ("TARGET", "", "Strike common: 133.5 MHz AM (BTN 2)"),
        # from the flight's comm_plan
        ("RECOVERY", "Spang Tower: 257.8 MHz AM (BTN 6)", ""),
    ]
    assert c["comms"]["intra"] == "276.5 MHz AM"
    assert all(
        "Shell" not in p["comm1"] for p in c["comms"]["phases"]
    )  # under tankers[]
    assert not has_warning(w, "comms.phases")


def test_unknown_activity_and_comm_plan_warn(docs):
    def mut(ato, res):
        viper(ato)["communications"][1]["activities"] = ["push", "nowhere"]
        viper(ato)["comm_plan"] = "no-such-plan"

    c, w = card_for(docs, mutate=mut)
    assert has_warning(w, "activity 'nowhere' is not an activity of the flight")
    assert has_warning(w, "comm_plan 'no-such-plan' is not in the resources")
    assert [p["phase"] for p in c["comms"]["phases"]] == [
        "ALL PHASES",
        "DEPARTURE",
        "PUSH",
    ]


def test_without_activities_everything_is_one_phase(docs):
    def mut(ato, res):
        f = viper(ato)
        f.pop("activities")
        f.pop("comm_plan")
        for a in f["communications"]:
            a.pop("activities", None)

    c, _ = card_for(docs, mutate=mut)
    (phase,) = c["comms"]["phases"]
    assert phase["phase"] == "ALL PHASES"
    assert phase["comm1"] == "Overlord control: 251.0 MHz AM (BTN 1)"
    assert phase["comm2"] == (
        "Strike common: 133.5 MHz AM (BTN 2) / Spang Ground: 121.8 MHz AM (BTN 3)"
    )


def test_mids_from_link16_flight_channels_and_lead_station(docs):
    c, w = card_for(docs)
    assert c["comms"]["mids"] == "Link 16 STN 01201 FTR 7 MSN 3 TEAM 01202/01203/01204"
    assert not has_warning(w, "comms.mids")


def test_link16_all_fields_and_flight_only(docs):
    def mut(ato, res):
        viper(ato)["configuration"]["member_overrides"][0]["identification"].pop(
            "link16"
        )
        viper(ato)["identification"]["link16"] = {
            "stn": "01300",
            "fighter_channel": 7,
            "mission_channel": 3,
            "special_channel": 4,
            "team": ["01301"],
            "donors": ["01400", "01401"],
        }

    c, _ = card_for(docs, mutate=mut)
    assert c["comms"]["mids"] == (
        "Link 16 STN 01300 FTR 7 MSN 3 SPL 4 TEAM 01301 DONOR 01400/01401"
    )


def test_mids_falls_back_to_the_datalink_text_fields(docs):
    def mut(ato, res):
        viper(ato)["configuration"]["member_overrides"][0]["identification"].pop(
            "link16"
        )
        ident = viper(ato)["identification"]
        ident.pop("link16")
        ident.update(
            datalink_type="Link 16", datalink_network="Net 1", datalink_station="01201"
        )

    c, w = card_for(docs, mutate=mut)
    assert c["comms"]["mids"] == "Link 16 Net 1 STN 01201"
    assert not has_warning(w, "comms.mids")


def test_timing_tot_and_push_from_the_package(docs):
    c, w = card_for(docs)
    assert c["timing"] == {
        "tot": "1030Z +/-5 MIN",
        "push": "0950Z",
        "push_point": "IVORY",  # the control measure's name, not its identifier
    }
    assert not has_warning(w, "timing")


@pytest.mark.parametrize(
    ("spec", "text"),
    [
        ({"kind": "at", "at": "2026-10-14T10:30:00Z"}, "1030Z"),
        (
            {"kind": "at", "at": "2026-10-14T10:30:00Z", "tolerance_seconds": 30},
            "1030Z +/-30 SEC",
        ),
        ({"kind": "at", "at": "2026-10-14T12:30:00+02:00"}, "1030Z"),
        ({"kind": "at", "at": {"offset_minutes": 150}}, "1030Z"),  # period starts 0800Z
        (
            {
                "kind": "window",
                "window": {
                    "start": "2026-10-14T10:30:00Z",
                    "end": {"offset_minutes": 165},
                },
            },
            "1030Z-1045Z",
        ),
        ({"kind": "not_after", "at": "2026-10-14T10:45:00Z"}, "NLT 1045Z"),
        ({"kind": "not_before", "at": "2026-10-14T10:15:00Z"}, "NET 1015Z"),
        (
            {"kind": "on_order", "condition": "SAM suppressed"},
            "ON ORDER: SAM suppressed",
        ),
    ],
)
def test_time_conditions_read_as_kneeboard_text(docs, spec, text):
    def mut(ato, res):
        ato["packages"][0]["time_on_target"] = spec

    c, _ = card_for(docs, mutate=mut)
    assert c["timing"]["tot"] == text


def test_timing_is_blank_with_warnings_when_the_package_gives_none(docs):
    def mut(ato, res):
        for k in ("time_on_target", "push_time", "push_point"):
            ato["packages"][0].pop(k)

    c, w = card_for(docs, mutate=mut)
    assert "timing" not in c
    assert has_warning(w, "Viper 1: timing.tot") and has_warning(w, "timing.push")

    def no_package(ato, res):
        ato["missions"][0].pop("package")

    c, w = card_for(docs, mutate=no_package)
    assert "timing" not in c and has_warning(
        w, "Viper 1: timing: mission has no package"
    )


def test_push_point_without_a_known_measure_shows_its_identifier(docs):
    def mut(ato, res):
        res["resources"]["control_measures"] = {}

    c, _ = card_for(docs, mutate=mut)
    assert c["timing"]["push_point"] == "push-ivory"


def test_baro_alt_from_the_opord_forecast_for_takeoff(docs):
    opord = json.loads(OPORD.read_text())
    c, w = card_for(docs, opord=opord)
    assert c["baro_alt"] == "29.92 inHg" and not has_warning(w, "baro_alt")

    def late(ato, res):  # takeoff in the second forecast window
        viper(ato)["launch"]["takeoff"] = "2026-10-14T13:00:00Z"

    c, _ = card_for(docs, mutate=late, opord=opord)
    assert c["baro_alt"] == "30.05 inHg"

    opord["situation"]["area_of_operations"]["weather"]["forecasts"][0]["altimeter"] = {
        "value": 1013.25,
        "unit": "hPa",
    }
    c, _ = card_for(docs, opord=opord)
    assert c["baro_alt"] == "1013.25 hPa"


def test_baro_alt_warns_without_an_opord_or_altimeter(docs):
    c, w = card_for(docs)
    assert c["baro_alt"] == "" and has_warning(w, "Viper 1: baro_alt: no OpenAIX opord")
    opord = json.loads(OPORD.read_text())
    for f in opord["situation"]["area_of_operations"]["weather"]["forecasts"]:
        f.pop("altimeter")
    c, w = card_for(docs, opord=opord)
    assert c["baro_alt"] == "" and has_warning(
        w, "the opord has no WeatherForecast.altimeter"
    )


def test_tankers(docs):
    c, _ = card_for(docs)
    (t,) = c["tankers"]
    assert (t["callsign"], t["frequency"], t["tacan"], t["button"]) == (
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
    assert c["tankers"] == [] and has_warning(w, "no Refueling mission")


def test_atc_from_launch_and_recovery_fields(docs):
    c, _ = card_for(docs)
    assert [(a["name"], a["frequency"]) for a in c["atc"]] == [
        ("ETAD GROUND", "121.8 MHz AM"),
        ("ETAD TOWER", "257.8 MHz AM"),
        ("ETAD APPROACH", "263.0 MHz AM"),
    ]


def test_atc_distinct_recovery_field(docs):
    def mut(ato, res):
        viper(ato)["recovery"]["destination"] = "etar"

    c, _ = card_for(docs, mutate=mut)
    assert c["atc"][-1]["name"] == "ETAR TOWER"


# ------------------------------------------------------------------- warnings


def test_missing_sources_warn_and_stay_blank(docs):
    def mut(ato, res):
        f = viper(ato)
        for k in (
            "fuel",
            "communications",
            "comm_plan",
            "identification",
            "launch",
            "recovery",
        ):
            f.pop(k)
        f["configuration"].pop("member_overrides")
        res["resources"]["scls"]["f16-oca"].pop("laser_code")
        ato["missions"][0]["tasking"].pop("objective")

    c, w = card_for(docs, mutate=mut)
    assert (
        c["comms"]["intra"] == ""
        and c["comms"]["mids"] == ""
        and c["comms"]["phases"] == []
    )
    assert c["atc"] == [] and c["primary_objectives"] == []
    assert c["fuel_plan"]["joker_lbs"] == 0 and c["fuel_plan"]["rcv_tank_lbs"] == 4000
    assert all(p["laser"] == "" for p in c["positions"])
    for field in (
        "positions[].laser",
        "tacan.flight",
        "primary_objectives",
        "positions[].modex",
        "positions[].pers",
        "fuel_plan.joker_lbs",
        "comms.intra",
        "comms.mids",
        "atc",
    ):
        assert has_warning(w, f"Viper 1: {field}"), field


# ----------------------------------------------------------------- YAML merge


# ------------------------------------------------------------------ overrides


def override(**kw):
    return {"flight_callsign": "VIPER1", **kw}


def test_override_modex_wins_field_by_field(docs):
    c, _ = card_for(docs)
    y = override(positions=[{"number": 1, "modex": "411"}])
    (m,), warns = merge([c], [y])
    assert m["positions"][0]["modex"] == "411"
    assert [p["laser"] for p in m["positions"]] == ["1688", "1687", "1688", "1688"]
    assert len(m["positions"]) == 4 and m["flight_callsign"] == "Viper 1"
    assert has_warning(
        warns, "positions[0].modex: YAML value '411' overrides ATO value '401'"
    )
    assert c["positions"][0]["modex"] == "401"  # inputs are not mutated

    def blank(ato, res):  # blank ATO board number: filling a blank is no disagreement
        for o in viper(ato)["configuration"]["member_overrides"]:
            o.pop("board_number")

    c, _ = card_for(docs, mutate=blank)
    (m,), warns = merge([c], [y])
    assert m["positions"][0]["modex"] == "411" and warns == []


def test_override_disagreement_warns(docs):
    c, _ = card_for(docs)
    y = override(
        positions=[{"number": 1, "laser": "1511"}],
        tacan={"lead": "99Y"},
        weaponeering="Different load",
    )
    (m,), warns = merge([c], [y])
    assert (m["positions"][0]["laser"], m["tacan"]["lead"], m["tacan"]["flight"]) == (
        "1511",
        "99Y",
        "77Y",
    )
    assert m["weaponeering"] == "Different load"
    assert len(warns) == 3
    assert has_warning(
        warns, "positions[0].laser: YAML value '1511' overrides ATO value '1688'"
    )
    assert has_warning(warns, "tacan.lead") and has_warning(warns, "weaponeering")


def test_equal_override_is_silent_and_unmatched_cards_are_kept(docs):
    c, _ = card_for(docs)
    other = {"flight_callsign": "Hawg 2"}
    merged, warns = merge([c], [override(msn_number="4101"), other])
    assert warns == [] and [m["flight_callsign"] for m in merged] == [
        "Viper 1",
        "Hawg 2",
    ]
    merged, _ = merge([c], [other], keep_unmatched=False)
    assert [m["flight_callsign"] for m in merged] == ["Viper 1"]


def test_bad_card_names_its_json_pointer():
    validate_cards([{"flight_callsign": "A"}])
    with pytest.raises(ValueError, match="/cards/1/tacan/lead"):
        validate_cards([{}, {"tacan": {"lead": 14}}])


# ------------------------------------------------------------------------ files


def write_ato_with_overrides(tmp_path, flight_card=None, top_cards=None):
    ato = json.loads(ATO.read_text())
    if flight_card:
        viper(ato).setdefault("extensions", {})[EXT] = {"cards": [flight_card]}
    if top_cards:
        ato.setdefault("extensions", {})[EXT] = {"cards": top_cards}
    path = tmp_path / "ato.json"
    path.write_text(json.dumps(ato))
    return path


def test_cards_from_files_builds_every_flight():
    cards, _ = cards_from_files(ATO, RES)
    assert [c["flight_callsign"] for c in cards] == ["Viper 1", "Shell 1"]
    cards, _ = cards_from_files(ATO, RES, "shell-1")
    assert [c["flight_callsign"] for c in cards] == ["Shell 1"]


def test_cards_from_files_rejects_wrong_kind():
    with pytest.raises(ValueError, match="expected an OpenAIX 'ato'"):
        cards_from_files(RES, RES)


def test_flight_extension_card_without_callsign_applies_to_its_flight(tmp_path):
    path = write_ato_with_overrides(
        tmp_path, flight_card={"notes": "Check in with AWACS", "tacan": {"lead": "99Y"}}
    )
    cards, warns = cards_from_files(path, RES)
    assert cards[0]["notes"] == "Check in with AWACS"
    assert cards[0]["tacan"] == {"lead": "99Y", "flight": "77Y"}
    assert has_warning(warns, "tacan.lead: YAML value '99Y' overrides ATO value '14Y'")
    assert "notes" not in cards[1]


def test_top_level_cards_merge_and_unmatched_are_added(tmp_path):
    path = write_ato_with_overrides(
        tmp_path,
        top_cards=[
            {"flight_callsign": "Viper 1", "weaponeering": "Own load"},
            {"flight_callsign": "Hawg 2", "msn_number": "9"},
        ],
    )
    cards, _ = cards_from_files(path, RES)
    assert [c["flight_callsign"] for c in cards] == ["Viper 1", "Shell 1", "Hawg 2"]
    assert cards[0]["weaponeering"] == "Own load"
    cards, _ = cards_from_files(path, RES, "viper-1")
    assert [c["flight_callsign"] for c in cards] == ["Viper 1"]


def test_cards_from_files_opord_adds_the_altimeter():
    cards, warns = cards_from_files(ATO, RES, "viper-1", OPORD)
    assert cards[0]["baro_alt"] == "29.92 inHg" and not has_warning(warns, "baro_alt")


def test_cards_from_document_reads_the_extension(tmp_path):
    path = tmp_path / "frago.yaml"
    doc = json.loads(OPORD.read_text())
    doc["extensions"] = {EXT: {"cards": [{"flight_callsign": "Hawg 2", "notes": "x"}]}}
    path.write_text(yaml.safe_dump(doc))
    assert cards_from_document(path) == [{"flight_callsign": "Hawg 2", "notes": "x"}]


# ----------------------------------------------------------------- rendering


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_render_cards_writes_numbered_768x1024_pngs(tmp_path):
    cards, _ = cards_from_files(ATO, RES)
    paths = render_cards(cards, tmp_path / "out", "op")
    assert [p.name for p in paths] == ["op_kneeboard_001.png", "op_kneeboard_002.png"]
    assert all(png_size(p) == (768, 1024) for p in paths)
    assert png_size(render_card_png(cards[0], tmp_path / "one.png")) == (768, 1024)


def test_sparse_card_renders_without_undefined():
    html = render_card_html({"flight_callsign": "Hawg 2", "positions": [{"number": 1}]})
    assert "Hawg 2" in html and "Undefined" not in html


def test_rendered_html_matches_golden(monkeypatch):
    monkeypatch.setattr(render, "stamp", lambda: STAMP)
    cards, _ = cards_from_files(ATO, RES, "viper-1", OPORD)
    html = render_card_html(cards[0])
    if os.environ.get(
        "UPDATE_GOLDEN"
    ):  # UPDATE_GOLDEN=1 uv run pytest tests/test_openaix_kneeboard.py
        GOLDEN.write_text(html, encoding="utf-8")
    assert html == GOLDEN.read_text(encoding="utf-8")


def test_golden_shows_the_gameplay_fields():
    """The committed golden carries the 0.2 fields: board number, crew, laser code, Link 16, TOT / push, radio
    phases and the altimeter setting."""
    html = GOLDEN.read_text(encoding="utf-8")
    for text in (
        '<td class="col-modex">401</td>',
        '<td class="col-pers">Viper / Jester</td>',
        '<td class="col-laser">1687</td>',
        "Link 16 STN 01201 FTR 7 MSN 3 TEAM 01202/01203/01204",
        "1030Z +/-5 MIN",
        "0950Z",
        "IVORY",
        '<div class="kb-phase-name">PUSH</div>',
        '<div class="kb-phase-name">RECOVERY</div>',
        "Spang Tower: 257.8 MHz AM (BTN 6)",
        "5,200 lbs",
        "29.92 inHg",
    ):
        assert text in html, text
