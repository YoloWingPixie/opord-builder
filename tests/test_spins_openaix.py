"""SPINS `openaix_table` blocks and the default typed-data layout."""

from __future__ import annotations

import json
import shutil
from itertools import pairwise
from pathlib import Path

import pytest
import yaml
from spinsdoc import native

from opord_builder._paths import SPINS_DEFAULT_LAYOUT
from opord_builder.load import DocumentError, load_document
from opord_builder.spins import (
    load_default_spins,
    load_spins,
    render_spins_html,
    render_spins_markdown,
)
from opord_builder.spins_openaix import format_value

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests/fixtures/openaix/steel-opera"
EXAMPLE = ROOT / "examples/operation-steel-opera/spins-openaix.yaml"


def spins_doc(blocks, **extra):
    return {
        "kind": "spins",
        "schema_version": "0.3",
        "scope": "standing",
        "meta": {"id": "t", "title": "T", "revision": "1"},
        "content": [{"kind": "section", "title": "S", "blocks": blocks}],
        **extra,
    }


def table(**kw):
    block = {
        "kind": "openaix_table",
        "caption": "Nets",
        "source": "spins",
        "pointer": "/communications/nets",
        "columns": [{"key": "net", "heading": "Net", "field": "/name"}],
    }
    block.update(kw)
    return block


@pytest.fixture
def workdir(tmp_path):
    for f in FIX.glob("*.json"):
        shutil.copy(f, tmp_path / f.name)
    return tmp_path


def write(tmp, blocks, refs=None, **extra):
    refs = (
        {"spins": "spins.json", "resources": "resources.json"} if refs is None else refs
    )
    path = tmp / "s.yaml"
    path.write_text(yaml.safe_dump(native(spins_doc(blocks, openaix=refs, **extra))))
    return path


def test_fixtures_are_valid_openaix_and_match_vendored_examples():
    vendored = ROOT / "opord_builder/openaix/vendor/examples/maximal"
    for name in ("spins", "resources", "airfield"):
        assert (FIX / f"{name}.json").read_bytes() == (
            vendored / f"{name}.json"
        ).read_bytes()


def test_example_renders_md_and_html():
    document = load_spins(EXAMPLE)
    md = render_spins_markdown(document)
    html = render_spins_html(document)
    for text in (
        "Darkstar control (251.0 MHz AM)",
        "FL180 to FL200",
        "63Y (SHL)",
        "7598 ft",
        "NOT PROVIDED",
    ):
        assert text in md
    assert "Darkstar control (251.0 MHz AM)" in html and "<table>" in html
    assert "Table 4" in md  # openaix tables share the table sequence


def test_entries_rows_use_map_keys():
    md = render_spins_markdown(load_spins(EXAMPLE))
    assert "| control-uhf | Darkstar control | 251.0 MHz AM |" in md


def test_default_layout_is_a_valid_shipped_resource():
    assert SPINS_DEFAULT_LAYOUT.name == "spins-default.yaml"
    load_document(SPINS_DEFAULT_LAYOUT)
    assert "opord_builder/templates/**/*" in (ROOT / "pyproject.toml").read_text()
    text = SPINS_DEFAULT_LAYOUT.read_text()
    assert "TODO(openaix" not in text
    for field in ("/carrier/link4", "/carrier/acls", "/carrier/recovery_windows"):
        assert field in text


def test_default_layout_renders_every_section():
    document = load_default_spins(
        spins=FIX / "spins.json",
        resources=FIX / "resources.json",
        airfields=[FIX / "airfield.json", FIX / "carrier.json"],
    )
    md = render_spins_markdown(document)
    for heading in (
        "Communications",
        "IFF",
        "Laser codes",
        "Tanker procedures",
        "Divert and abort",
        "Recovery routing",
        "Weather minimums",
        "Carrier",
    ):
        assert f" {heading}\n" in md
    assert "OIR Special Instructions" in md  # title taken from the typed document
    assert "TUMBLEWEED" in md and "1688" in md and "CVN-72" in md
    assert "Muwaffaq Salti (OJMS)" in md  # airfield identifiers resolved
    assert "6000 ft MSL" in md and "180° M" in md
    assert "Marshal 264.0 MHz AM" in md
    assert "<h2" in render_spins_html(document)


def test_carrier_table_shows_link4_acls_and_recovery_windows():
    document = load_default_spins(airfields=[FIX / "carrier.json"])
    md = render_spins_markdown(document)
    carrier = md[md.index(" Carrier\n") :]
    for text in (
        "Link 4",
        "335.4 MHz",
        "ACLS",
        "Recovery windows",
        "Case I 021300ZOCT26 to 021400ZOCT26, BRC 090° M",
        "Case III 021400ZOCT26 to 021500ZOCT26",
    ):
        assert text in carrier, text
    assert "Yes" in carrier  # acls: true


def test_recovery_window_text_form():
    window = {
        "case": "case_ii",
        "window": {"start": "2026-10-02T13:00:00Z", "end": "2026-10-02T14:00:00Z"},
    }
    assert format_value(window) == "Case II 021300ZOCT26 to 021400ZOCT26"
    window["brc"] = {"value": 270, "reference": "true"}
    assert format_value([window]).endswith(", BRC 270° T")


def test_default_layout_skips_absent_sections_without_empty_headings():
    document = load_default_spins(
        spins=FIX / "spins.json"
    )  # no airfields, no resources
    md = render_spins_markdown(document)
    assert " Carrier\n" not in md
    assert " Communications\n" in md
    # no heading is immediately followed by another heading
    lines = [
        line
        for line in md.splitlines()
        if line.strip() and not line.startswith("<a id")
    ]
    for first, second in pairwise(lines):
        assert not (first.startswith("## ") and second.startswith("## "))


def test_default_layout_with_no_data_has_no_sections():
    document = load_default_spins()
    assert document.content == []
    assert "##" not in render_spins_markdown(document)


def test_skip_removes_block_and_notice_prints_not_provided(workdir):
    path = write(
        workdir,
        [
            table(pointer="/nowhere", empty="skip"),
            table(pointer="/nowhere", empty="notice", caption="Gone"),
        ],
    )
    md = render_spins_markdown(load_spins(path))
    assert "NOT PROVIDED" in md and "Gone" in md and "Nets" not in md


def test_all_children_skipped_drops_the_section(workdir):
    path = write(workdir, [table(pointer="/nowhere", empty="skip")])
    assert load_spins(path).content == []


def test_missing_data_is_an_error_by_default_naming_block_and_pointer(workdir):
    path = write(workdir, [table(id="nets", pointer="/nowhere")])
    with pytest.raises(ValueError, match=r"openaix_table 'nets'.*'/nowhere'"):
        load_spins(path)


def test_source_not_configured_is_absent_data(workdir):
    path = write(workdir, [table(source="ato", pointer="/missions")], refs={})
    with pytest.raises(ValueError, match="no ato file is listed"):
        load_spins(path)


def test_pointer_through_a_scalar_is_an_error(workdir):
    path = write(workdir, [table(id="bad", pointer="/communications/remarks/x")])
    with pytest.raises(
        ValueError,
        match=r"openaix_table 'bad'.*'/communications/remarks/x'.*cannot descend",
    ):
        load_spins(path)


def test_pointer_to_a_scalar_is_an_error(workdir):
    path = write(workdir, [table(id="bad", pointer="/communications/remarks")])
    with pytest.raises(ValueError, match="point at an array, a map or an object"):
        load_spins(path)


def test_rows_items_on_an_object_is_an_error(workdir):
    path = write(workdir, [table(id="bad", pointer="/communications", rows="items")])
    with pytest.raises(ValueError, match="must be an array"):
        load_spins(path)


def test_column_pointing_at_an_unreadable_object_names_the_column(workdir):
    block = table(
        id="bad",
        columns=[{"key": "x", "heading": "X", "field": "/extensions"}],
        pointer="",
    )
    with pytest.raises(
        ValueError, match=r"openaix_table 'bad': column 'x'.*no text form"
    ):
        load_spins(write(workdir, [block]))


@pytest.mark.parametrize("pointer", ["no-slash", "/bad~2escape"])
def test_malformed_pointers_fail_extension_validation(workdir, pointer):
    with pytest.raises(
        DocumentError, match=r"/extensions/org.opord-builder.spins/content/0/blocks/0"
    ):
        load_spins(write(workdir, [table(pointer=pointer)]))
    with pytest.raises(DocumentError):
        load_spins(
            write(
                workdir,
                [table(columns=[{"key": "a", "heading": "A", "field": pointer}])],
            )
        )


def test_invalid_openaix_file_is_rejected_with_pointer(workdir):
    data = json.loads((workdir / "spins.json").read_text())
    data["communications"]["nets"][0]["channel"] = "Not An Identifier"
    (workdir / "spins.json").write_text(json.dumps(data))
    with pytest.raises(
        ValueError, match=r"not valid OpenAIX.*/communications/nets/0/channel"
    ):
        load_spins(write(workdir, [table()]))


def test_wrong_kind_missing_and_malformed_files(workdir):
    with pytest.raises(ValueError, match="kind is 'resources', expected \\['spins'\\]"):
        load_spins(write(workdir, [table()], refs={"spins": "resources.json"}))
    with pytest.raises(ValueError, match="nope.json"):
        load_spins(write(workdir, [table()], refs={"spins": "nope.json"}))
    (workdir / "bad.json").write_text("{")
    with pytest.raises(ValueError, match="bad.json"):
        load_spins(write(workdir, [table()], refs={"spins": "bad.json"}))


def test_require_drops_rows_and_lookup_falls_back_to_the_identifier(workdir):
    block = table(
        pointer="/divert_and_abort/divert_airfields",
        columns=[
            {"key": "a", "heading": "A", "field": "/airfield", "lookup": "airfield"},
            {"key": "c", "heading": "C", "field": "/conditions"},
        ],
        require=["/conditions"],
    )
    refs = {"spins": "spins.json", "airfields": ["airfield.json"]}
    md = render_spins_markdown(load_spins(write(workdir, [block], refs=refs)))
    assert "| h4 | East of 38E only |" in md and "prince-hassan" not in md


def test_cross_reference_to_a_skipped_block_is_a_clear_error(workdir):
    ref = {"kind": "paragraph", "text": [{"target": "gone"}]}
    path = write(workdir, [table(id="gone", pointer="/nowhere", empty="skip"), ref])
    with pytest.raises(ValueError, match="cross-reference to 'gone'"):
        load_spins(path)


def test_relative_paths_resolve_from_the_yaml(workdir):
    sub = workdir / "sub"
    sub.mkdir()
    path = sub / "s.yaml"
    path.write_text(
        yaml.safe_dump(native(spins_doc([table()], openaix={"spins": "../spins.json"})))
    )
    assert "Darkstar control" in render_spins_markdown(load_spins(path))


@pytest.mark.parametrize(
    ("value", "text"),
    [
        ({"value": 243, "unit": "MHz", "modulation": "AM"}, "243.0 MHz AM"),
        ({"value": 150, "unit": "flight_level", "reference": "FL"}, "FL150"),
        ({"value": 12000, "unit": "ft", "reference": "MSL"}, "12000 ft MSL"),
        ({"lower": {"surface": True}, "upper": {"unlimited": True}}, "SFC to UNL"),
        ({"value": 40, "unit": "nm"}, "40 nm"),
        ({"value": 350, "unit": "kt"}, "350 kt"),
        ({"channel": 63, "band": "Y", "identifier": "SHL"}, "63Y (SHL)"),
        ({"value": 74.9, "reference": "magnetic"}, "074.9° M"),
        ("2026-10-02T13:00:00Z", "021300ZOCT26"),
        ({"offset_minutes": -15}, "T-15 min"),
        (True, "Yes"),
        (["a", "b"], "a, b"),
        (None, ""),
    ],
)
def test_format_value(value, text):
    assert format_value(value) == text


def test_amendment_can_add_an_openaix_table(workdir):
    base = spins_doc(
        [{"kind": "paragraph", "id": "p", "text": "x"}], openaix={"spins": "spins.json"}
    )
    (workdir / "base.yaml").write_text(yaml.safe_dump(native(base)))
    mission = spins_doc([], scope="mission", openaix={"spins": "spins.json"})
    mission["content"] = []
    mission["meta"]["id"] = "m"
    mission["period"] = {"start": "2026-10-02T13:00:00Z", "end": "2026-10-02T15:00:00Z"}
    mission["base"] = {"id": "t", "revision": "1", "path": "base.yaml"}
    mission["changes"] = [
        {
            "op": "add",
            "block": {"kind": "section", "title": "Nets", "blocks": [table()]},
        }
    ]
    (workdir / "m.yaml").write_text(yaml.safe_dump(native(mission)))
    assert "Darkstar control" in render_spins_markdown(load_spins(workdir / "m.yaml"))
