"""The comms standard fills the blank comm-card cells of the flight it names; the ATO value always wins."""

from __future__ import annotations

import json
from pathlib import Path

from opord_builder.kneeboard import build_cards, cards_from_files, merge_resources
from opord_builder.openaix.registry import VENDOR_DIR

FIX = Path(__file__).parent / "fixtures" / "openaix" / "atomic-thunder"
STANDARD = VENDOR_DIR / "standards" / "csg8" / "comms-standard.json"
GOLDEN = Path(__file__).parent / "golden" / "ripper-1-standard.json"


def build(callsign="Ripper 1", blank=False, standard=True):
    ato = json.loads((FIX / "ato.json").read_text())
    res = json.loads((FIX / "resources.json").read_text())
    flight = ato["missions"][0]["flights"][0]
    flight["callsign"] = callsign
    if blank:
        flight.pop("identification")
        flight["communications"] = [
            a for a in flight["communications"] if a["purpose"] != "Intraflight"
        ]
        flight["configuration"]["member_overrides"] = []
        flight["configuration"].pop("primary_scl")
    std = json.loads(STANDARD.read_text()) if standard else None
    cards, warns = build_cards(
        ato,
        merge_resources(ato, {"resources": res["resources"]}),
        "viper-1",
        None,
        std,
    )
    return cards[0], warns


def view(card, warns):
    return {
        "lasers": [p["laser"] for p in card["positions"]],
        "tacan": card["tacan"],
        "intra": card["comms"]["intra"],
        "mids": card["comms"]["mids"],
        "warnings": [w for w in warns if "comms standard" in w],
    }


def test_blank_cells_are_filled_from_the_standard_golden():
    assert view(*build(blank=True)) == json.loads(GOLDEN.read_text())


def test_a_flight_the_standard_does_not_name_is_unchanged():
    assert build("Viper 1") == build("Viper 1", standard=False)


def test_ato_value_wins_and_the_difference_warns():
    card, warns = build()
    assert card["tacan"] == {"lead": "14Y", "flight": "77Y"}
    assert (
        card["comms"]["mids"] == "Link 16 STN 01201 FTR 7 MSN 3 TEAM 01202/01203/01204"
    )
    assert any("tacan.lead" in w and "differs from comms standard" in w for w in warns)
    assert any("positions[2].laser" in w and "'1687'" in w for w in warns)


def test_the_card_needs_no_standard():
    card, warns = build("Ripper 1", blank=True, standard=False)
    assert card["tacan"] == {"lead": "", "flight": ""}
    assert not any("comms standard" in w for w in warns)


def test_cards_from_files_takes_the_standard():
    cards, warns = cards_from_files(FIX / "ato.json", standard_path=STANDARD)
    assert cards and not any("comms standard" in w for w in warns)


def test_spins_comms_example_renders_the_standard_quickly():
    import time

    from opord_builder.spins import load_spins, render_spins_markdown

    start = time.perf_counter()
    md = render_spins_markdown(
        load_spins(Path(__file__).parent.parent / "examples/spins-comms.yaml")
    )
    assert time.perf_counter() - start < 2
    for text in (
        "| RIPPER | RIPPER INTRAFLIGHT (275.0 MHz AM) | 8Y | 71Y | RP | 0410 |",
        "| ARCO11 | tanker |",
        "| VF-11 | 04 | 10 |",
        "| ripper | 1511 |",
    ):
        assert text in md
