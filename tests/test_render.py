"""Rendering OpenAIX orders: examples, committed outputs, no content loss, FRAGO and WARNO, products."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from opord_builder import render
from opord_builder.format import RFC3339, dtg, fmt, has_content, humanize, letter_for
from opord_builder.frago import StaleBaseError
from opord_builder.load import read
from opord_builder.order import load_order

REPO = Path(__file__).resolve().parent.parent
EXAMPLES = REPO / "examples"
VENDOR = REPO / "opord_builder" / "openaix" / "vendor" / "examples"
ORDERS = [
    "example_full",
    "example_minimal",
    "example_hybrid",
    "example_with_sources",
    "example_full_with_sources",
]
DELTAS = ["frago_01_iron_strike", "warno_01_iron_strike", "warno_standalone"]
COMMITTED = ["example_full", "example_minimal"]


@pytest.fixture(scope="session")
def orders():
    return {n: load_order(EXAMPLES / f"{n}.yaml") for n in ORDERS + DELTAS}


@pytest.mark.parametrize("name", ORDERS + DELTAS)
def test_every_example_renders(orders, name):
    o = orders[name]
    md, html = render.render_markdown(o), render.render_html(o)
    assert md.strip() and html.startswith("<!DOCTYPE html>")
    assert "UNCLASSIFIED" in md and "UNCLASSIFIED" in html
    assert "None" not in md  # an absent value never prints as text


@pytest.mark.parametrize("kind", ["minimal", "maximal"])
def test_vendored_examples_render(kind, tmp_path):
    base = json.loads((VENDOR / kind / "opord.json").read_text())
    base["meta"] = (
        {**base.get("meta", {}), "id": "oir-opord", "revision": "1"}
        if kind == "minimal"
        else base["meta"]
    )
    base_path = tmp_path / "base.json"
    base_path.write_text(json.dumps(base))
    assert render.render_markdown(load_order(VENDOR / kind / "opord.json")).strip()
    frago = load_order(
        VENDOR / kind / "frago.json",
        base_path if kind == "minimal" else VENDOR / kind / "opord.json",
    )
    assert frago.kind == "frago" and render.render_html(frago)


# --------------------------------------------------------------------------- committed outputs


def serial(html: str) -> str:
    return re.search(r'data-serial="([^"]+)"', html).group(1)


@pytest.mark.parametrize("name", COMMITTED)
def test_committed_outputs_are_reproduced(name, monkeypatch):
    html = (EXAMPLES / f"{name}.html").read_text(encoding="utf-8")
    monkeypatch.setattr(render, "stamp", lambda *_: serial(html))
    o = load_order(EXAMPLES / f"{name}.yaml")
    assert render.render_markdown(o) == (EXAMPLES / f"{name}.md").read_text(
        encoding="utf-8"
    )
    assert render.render_html(o) == html


# --------------------------------------------------------------------------- nothing is lost

# Identifiers, references and codes that the rendering shows by name, as a heading, or not at all.
UNPRINTED = re.compile(
    r"^/(\$schema|schema_version|kind|resources_ref|meta/(id|revision|issued_at|issuing_unit|operation|author|title))"
    r"|/(id|parent|target|unit|to|channel_ref|resources_path|status|base_order_path|document_kind|logo|page_icon|watermark)$"
    r"|/(relationship|kind|mark|friendly_direction)$|^/references/\d+/id$"
    r"|^/(task_organization|command_and_signal/signal/channels|annexes/C/airspace/measures|annexes/D/fire_support_coordination_measures)"
    r"|/threats/\d+$|^/base_order|^/changes/"
)


def leaves(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from leaves(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from leaves(v, f"{path}/{i}")
    elif isinstance(node, str) and node.strip():
        yield path, node


def touched(path: str, shown: set[str]) -> bool:
    """Does the FRAGO print the paragraph or annex this document path lies in?"""
    keys = path.split("/")[1:]
    if keys[0] == "extensions":
        keys = keys[2:] if keys[1].endswith(".order") else []
    return bool(keys) and (
        f"annex:{keys[1]}" in shown
        if keys[0] == "annexes" and len(keys) > 1
        else keys[0] in shown
    )


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@pytest.mark.parametrize("name", ORDERS + DELTAS)
def test_no_content_is_lost(orders, name):
    o = orders[name]
    md = squash(render.render_markdown(o))
    docs = [o.head, o.doc] if o.kind == "frago" else [o.doc]
    lost = [
        (p, s[:60])
        for doc in docs
        for p, s in leaves(doc)
        if not UNPRINTED.search(p)
        and (o.shown is None or doc is o.head or touched(p, o.shown))
        and squash(dtg(s) if RFC3339.fullmatch(s) else fmt(s)) not in md
    ]
    assert not lost, lost[:10]


# --------------------------------------------------------------------------- shape of the output


def test_sections_without_content_are_left_out(orders):
    md = render.render_markdown(orders["example_minimal"])
    assert "## 1. (U) Situation" not in md and "## 2. (U) Mission" in md
    assert "### 1." not in md


def test_paragraphs_are_lettered_without_gaps(orders):
    md = render.render_markdown(orders["example_full"])
    letters = re.findall(r"^(?:### |\*\*)3\.([a-z])\. ", md, re.MULTILINE)
    assert letters == [letter_for(i) for i in range(1, len(letters) + 1)]


def test_annex_directory_lists_every_letter_and_reserved_ones(orders):
    rows = {d["letter"]: d for d in render.directory(orders["example_minimal"])}
    assert (
        len(rows) == 26
        and rows["I"]["status"] == "not_used"
        and rows["B"]["status"] == "omitted"
    )
    full = {d["letter"]: d["status"] for d in render.directory(orders["example_full"])}
    assert full["C"] == "published" and full["T"] == "not_used"


def test_classification_banner_and_copy_line(orders):
    md = render.render_markdown(orders["example_full"]).splitlines()
    assert md[0] == "**UNCLASSIFIED**" and "Copy 3 of 24 copies" in md[2]
    assert md[-1] == "**UNCLASSIFIED**"


def test_text_watermark_is_an_svg_data_url():
    assert render.watermark_from_value("DRAFT").startswith("data:image/svg+xml;base64,")
    assert render.watermark_from_value(None) == ""


def test_formatters():
    assert dtg("2026-04-18T12:00:00Z") == "181200ZAPR26"
    assert fmt({"value": 20000, "unit": "ft", "reference": "MSL"}) == "20000 ft MSL"
    assert fmt({"value": 251, "unit": "MHz", "modulation": "AM"}) == "251.0 MHz AM"
    assert fmt({"channel": 63, "band": "Y"}) == "63Y"
    assert fmt({"latitude": 50.0, "longitude": 7.0}).startswith("32U")
    assert (
        humanize("scheme_of_fires") == "Scheme of Fires"
        and humanize("cap_tracks") == "CAP Tracks"
    )
    assert letter_for(1) == "a" and letter_for(27) == "aa"
    assert not has_content({"a": [None, ""]}) and has_content({"a": ["x"]})


# --------------------------------------------------------------------------- FRAGO and WARNO


def test_frago_renders_touched_paragraphs_and_stubs_the_rest(orders):
    o = orders["frago_01_iron_strike"]
    assert o.shown >= {"situation", "execution", "annex:B", "annex:D"}
    md = render.render_markdown(o)
    assert "## 2. (U) Mission\n\n*No change from base OPORD 26-04.*" in md
    assert "### Annex B — Intelligence — Updated" in md and "### Annex C" not in md
    assert (
        "UPDATE (BCT Puma FMV" in md
    )  # the changed enemy activity is in the merged paragraph


def test_frago_with_stale_base_fails(tmp_path):
    base = read(EXAMPLES / "example_full.yaml")
    base["meta"]["revision"] = "2"
    (tmp_path / "base.yaml").write_text(yaml.safe_dump(base))
    with pytest.raises(StaleBaseError, match="revision"):
        load_order(EXAMPLES / "frago_01_iron_strike.yaml", tmp_path / "base.yaml")


def test_frago_needs_a_base(tmp_path):
    doc = read(EXAMPLES / "frago_01_iron_strike.yaml")
    del doc["extensions"]["org.opord-builder.order"]["base_order_path"]
    (tmp_path / "f.yaml").write_text(yaml.safe_dump(doc))
    with pytest.raises(ValueError, match="base"):
        load_order(tmp_path / "f.yaml")


def test_warno_marks_missing_paragraphs_to_be_published(orders):
    md = render.render_markdown(orders["warno_standalone"])
    assert md.count("*To be published in forthcoming OPORD.*") == 3
    assert "# WARNO 01 for OPORD TBP" in md


# --------------------------------------------------------------------------- products


def test_products_join_the_extension_to_the_typed_records(orders):
    o = orders["example_full"]
    found = {a: n for a, _, n in render.discover_products(o) if a}
    assert (
        found["jpitl"] == 3
        and found["cap_tracks"] == 3
        and found["subordinate_tasks"] == 6
    )
    header = render.render_product_csv(o, "cap_tracks").splitlines()[0].split(",")
    assert (
        header[0] == "name" and "altitude" in header and "controller_callsign" in header
    )


def test_a_product_can_be_a_json_pointer(orders):
    csv_text = render.render_product_csv(
        orders["example_full"], "/execution/tasks_to_subordinate_units"
    )
    assert csv_text.startswith("unit,tasks")


def test_product_html_has_the_order_header(orders):
    html = render.render_product_html(orders["example_full"], "jpitl")
    assert "Joint Prioritized Integrated Target List" in html and "OPORD" in html


def test_generic_walk_joins_extra_fields_by_identifier(orders):
    md = render.render_markdown(orders["example_full"])
    assert "| Name | Coordinates | Altitude Ft | Kind | TACAN Channel |" in md


def test_a_frago_applied_to_its_base_still_validates(orders):
    from opord_builder.load import validate_document

    assert validate_document(orders["frago_01_iron_strike"].doc) == []


# --------------------------------------------------------------------------- typed weather


def test_weather_formatters():
    from opord_builder.format import altimeter, clouds, forecast_line, forecast_row

    assert altimeter({"value": 29.92, "unit": "inHg"}) == "A2992"
    assert altimeter({"value": 1013, "unit": "hPa"}) == "Q1013"
    layers = [
        {"coverage": "few", "base": {"value": 3000, "unit": "ft", "reference": "AGL"}},
        {
            "coverage": "broken",
            "base": {"value": 8000, "unit": "ft", "reference": "AGL"},
        },
    ]
    assert clouds(layers) == "FEW030 BKN080"
    f = {
        "clouds": layers,
        "visibility": {"value": 10, "unit": "km"},
        "wind_speed": {"value": 12, "unit": "kt"},
    }
    assert forecast_line(f) == "FEW030 BKN080 · VIS 10 km · WIND 12 kt"
    row = forecast_row(
        {"visibility": {"value": 10, "unit": "km"}}, {"visibility": "afternoon haze"}
    )
    assert (
        row["visibility"] == "10 km; afternoon haze"
    )  # the note holds what the typed field could not


def test_paragraph_one_prints_a_forecast_table_from_typed_weather(orders):
    md = render.render_markdown(orders["example_full"])
    assert (
        "| Period | Surface Wind | Visibility | Clouds | Temperature | Precipitation | Effects |"
        in md
    )
    assert (
        "| 10 km; afternoon SCT 5,000 ft. |" in md
    )  # a typed 10 km with the text that remains
    assert "| Date | BMNT | Sunrise | Sunset | EENT | Moonrise | Moonset | Moon |" in md
    assert "| 2026-04-19 | 190518ZAPR26 |" in md and "waxing gibbous 62%" in md


def test_forecast_table_columns_follow_the_typed_values():
    o = load_order(REPO / "tests/fixtures/openaix/atomic-thunder/opord.json")
    md = render.render_markdown(o)
    assert "| Period | Clouds | Altimeter | Winds Aloft |" in md
    assert (
        "| 140800ZOCT26 to 141200ZOCT26 | SCT040 | A2992 | 18000 ft MSL 270° T / 35 kt |"
        in md
    )


def headings(md: str, para: int) -> list[str]:
    """The `###` subparagraph headings of one paragraph, without their letters."""
    body = md.split(f"## {para}. (U)")[1].split("\n## ")[0]
    return re.findall(r"^### \d\.[a-z]+\. (.+)$", body, re.MULTILINE)


def test_subparagraphs_follow_doctrinal_order(orders):
    md = render.render_markdown(orders["example_full"])
    assert headings(md, 1) == [
        "Area of Interest", "Area of Operations", "Enemy Forces", "Friendly Forces",
        "Interagency, Intergovernmental, and Nongovernmental Organizations",
        "Civil Considerations (ASCOPE)", "Attachments and Detachments", "Assumptions",
    ]  # fmt: skip
    three = headings(md, 3)
    assert three[:3] == [
        "Commander's Intent",
        "Concept of Operations",
        "Scheme of Movement and Maneuver",
    ]
    assert three[-3:] == [
        "Assessment",
        "Tasks to Subordinate Units",
        "Coordinating Instructions",
    ]
    assert three.index("Scheme of Reconnaissance and Security") < three.index(
        "Scheme of Intelligence"
    )
    assert (
        three.index("Scheme of Protection")
        < three.index("Stability")
        < three.index("Scheme of Engineer Operations")
    )
    assert headings(md, 5) == ["Command", "Control", "Signal"]
    assert not re.search(
        r"^\*\*[1-5]\.[a-z]\.", md, re.MULTILINE
    )  # no lettered subparagraph in bold


# --------------------------------------------------------------------------- determinism


def test_stamp_is_the_issue_time_and_renders_repeat(tmp_path, monkeypatch):
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    path = EXAMPLES / "example_minimal.yaml"
    o = load_order(path)
    when = o.head["meta"].get("issued_at") or o.head["date_time"]
    assert render.stamp(o.head) == dtg(when)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", str(render.issued_epoch(o.head)))
    for run in ("a", "b"):
        render.render_all(o, tmp_path / run, "x")
    for name in ("x.md", "x.html", "x.pdf"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
