"""Temporary proof that the migrated native documents lose nothing: rendering them through the old renderer
(native -> flat stash -> from_openaix -> model) reproduces, byte for byte, the output of the original authoring files."""

from __future__ import annotations

from pathlib import Path

import pytest

import opord_builder.renderer as R
from opord_builder.spins import load_spins, render_spins_html, render_spins_markdown

REPO = Path(__file__).resolve().parent.parent
E = REPO / "examples"
GOLDEN = Path(__file__).resolve().parent / "golden"
OPORDS = [
    "example_full",
    "example_minimal",
    "example_hybrid",
    "example_with_sources",
    "example_full_with_sources",
]
SPINS = {
    "spins-example": E / "spins-example.yaml",
    "spins-standing": E / "spins-standing.yaml",
    "operation-steel-opera-spins": E / "operation-steel-opera/spins.yaml",
    "operation-steel-opera-spins-openaix": E
    / "operation-steel-opera/spins-openaix.yaml",
}


@pytest.fixture(autouse=True)
def frozen_stamp(monkeypatch):
    monkeypatch.setattr(R, "_now_utc_stamp", lambda: "010000ZJAN26")


def same(stem: str, md: str, html: str) -> None:
    assert md == (GOLDEN / f"{stem}.md").read_text(encoding="utf-8")
    assert html == (GOLDEN / f"{stem}.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", OPORDS)
def test_opord(name):
    o = R.load_opord(E / f"{name}.yaml")
    same(name, R.render_markdown(o), R._inline_stylesheet(R.render_html(o)))


def test_frago():
    f, b = R.load_frago(E / "frago_01_iron_strike.yaml")
    same(
        "frago_01_iron_strike",
        R.render_frago_markdown(f, b),
        R._inline_stylesheet(R.render_frago_html(f, b)),
    )
    for i, card in enumerate(f.kneeboards):
        html = R.render_kneeboard_html(card, i)
        assert html == (
            GOLDEN / f"frago_01_iron_strike.kneeboard-{i + 1}.html"
        ).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["warno_01_iron_strike", "warno_standalone"])
def test_warno(name):
    w, b = R.load_warno(E / f"{name}.yaml")
    same(
        name,
        R.render_warno_markdown(w, b),
        R._inline_stylesheet(R.render_warno_html(w, b)),
    )


@pytest.mark.parametrize("stem", SPINS)
def test_spins(stem):
    d = load_spins(SPINS[stem])
    same(stem, render_spins_markdown(d), render_spins_html(d))
