"""End-to-end render tests for the OPORD builder."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from opord_builder.renderer import (
    has_content,
    letter_for,
    load_opord,
    render_all,
    render_html,
    render_html_standalone,
    render_markdown,
)
from opord_builder.schema import OPORD, Annex, AnnexStatus

REPO = Path(__file__).resolve().parent.parent
FULL = REPO / "examples" / "example_full.yaml"
MINIMAL = REPO / "examples" / "example_minimal.yaml"


@pytest.fixture(scope="session")
def full_opord() -> OPORD:
    return load_opord(FULL)


@pytest.fixture(scope="session")
def minimal_opord() -> OPORD:
    return load_opord(MINIMAL)


# ---------------------------------------------------------------------------
# has_content behaviour
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value, expected",
    [
        (None, False),
        ("", False),
        ("   ", False),
        ("x", True),
        ([], False),
        ([None, "", []], False),
        (["x"], True),
        ({}, False),
        ({"a": None, "b": ""}, False),
        ({"a": "x"}, True),
        (0, False),
        (1, True),
    ],
)
def test_has_content_primitives(value, expected):
    assert has_content(value) is expected


def test_has_content_pydantic_model():
    o_empty = OPORD.model_validate(
        {
            "header": {
                "classification": "UNCLASSIFIED",
                "issuing_headquarters": "HQ",
                "place_of_issue": "X",
                "dtg": "Z",
                "operation_order_number": "1",
                "operation_name": "N",
                "time_zone": "Z",
            },
            "mission": "placeholder",
        }
    )
    # Situation is None in this minimal model: has_content must be False.
    assert has_content(o_empty.situation) is False
    assert has_content(o_empty.header) is True
    assert has_content(o_empty) is True


# ---------------------------------------------------------------------------
# letter_for
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "n, expected",
    [(1, "a"), (2, "b"), (26, "z"), (27, "aa"), (52, "az"), (53, "ba")],
)
def test_letter_for(n, expected):
    assert letter_for(n) == expected


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------
def test_missing_required_fields_raises():
    with pytest.raises(ValidationError):
        OPORD.model_validate({"header": {}, "mission": "x"})


def test_reserved_annex_letter_rejected():
    with pytest.raises(ValidationError):
        Annex(letter="I", status=AnnexStatus.PUBLISHED, body="x")


def test_reserved_annex_letter_accepted_as_not_used():
    a = Annex(letter="I", status=AnnexStatus.NOT_USED)
    assert a.letter == "I"


def test_typo_in_field_name_rejected():
    data = yaml.safe_load(FULL.read_text())
    data["mission_statement"] = "oops"  # typo, should be `mission`
    with pytest.raises(ValidationError):
        OPORD.model_validate(data)


# ---------------------------------------------------------------------------
# Render: full
# ---------------------------------------------------------------------------
def test_full_example_validates(full_opord: OPORD):
    assert full_opord.header.operation_name == "IRON STRIKE"
    assert full_opord.mission.strip().startswith("TF IRON attacks")
    assert len(full_opord.execution.tasks_to_subordinate_units) == 6


def test_full_markdown_includes_every_paragraph(full_opord: OPORD):
    md = render_markdown(full_opord)
    for heading in [
        "## 1. (U) Situation",
        "## 2. (U) Mission",
        "## 3. (U) Execution",
        "## 4. (U) Sustainment",
        "## 5. (U) Command and Signal",
    ]:
        assert heading in md, f"missing {heading}"
    assert "IRON STRIKE" in md
    assert "OAKOC" in md
    assert "ASCOPE" in md


def test_full_pdf_renders(tmp_path: Path, full_opord: OPORD):
    outputs = render_all(
        full_opord, tmp_path, "full",
        write_markdown=False, write_html=False, write_pdf=True,
    )
    pdf = outputs["pdf"]
    assert pdf.exists()
    size = pdf.stat().st_size
    assert size > 20_000, f"pdf suspiciously small: {size} bytes"
    header = pdf.read_bytes()[:5]
    assert header == b"%PDF-"


def test_full_html_standalone_is_self_contained(tmp_path: Path, full_opord: OPORD):
    outputs = render_all(
        full_opord, tmp_path, "full",
        write_markdown=False, write_html=True, write_pdf=False,
    )
    html_path = outputs["html"]
    content = html_path.read_text()
    # Doctype + body present.
    assert content.startswith("<!DOCTYPE html>") or "<!DOCTYPE html>" in content[:200]
    assert "<body" in content
    # Stylesheet is inlined — a signature rule should appear directly in the file.
    assert ".cover-hero" in content, "styles.css was not inlined"
    assert ".para-num" in content
    # No external <link rel=stylesheet> (we inlined everything).
    assert 'rel="stylesheet"' not in content
    # Operation name appears.
    assert "IRON STRIKE" in content


# ---------------------------------------------------------------------------
# Render: minimal — the "no blank sections" guarantee
# ---------------------------------------------------------------------------
def test_minimal_markdown_skips_empty_paragraphs(minimal_opord: OPORD):
    md = render_markdown(minimal_opord)
    # Mission is required — it must render.
    assert "## 2. (U) Mission" in md
    # Intent has one populated field — Execution must render.
    assert "## 3. (U) Execution" in md
    # Situation, Sustainment, C&S must NOT render because none were provided.
    assert "## 1. (U) Situation" not in md
    assert "## 4. (U) Sustainment" not in md
    assert "## 5. (U) Command and Signal" not in md


def test_minimal_markdown_renders_only_purpose_under_intent(minimal_opord: OPORD):
    md = render_markdown(minimal_opord)
    # Intent card present.
    assert "Commander's Intent" in md
    # Purpose present.
    assert "Purpose." in md
    # Key Tasks and End State must be absent.
    assert "Key Tasks." not in md
    assert "End State." not in md


def test_minimal_html_has_no_empty_cards(minimal_opord: OPORD):
    html = render_html(minimal_opord)
    # Sanity: mission block is present.
    assert "mission-text" in html
    # No card for situation / sustainment / command-and-signal.
    # These would normally each be `<section class="paragraph para-N">`.
    for dead in ["para-1", "para-4", "para-5"]:
        assert f'class="paragraph {dead}"' not in html, f"{dead} rendered despite being empty"


def test_minimal_pdf_renders(tmp_path: Path, minimal_opord: OPORD):
    outputs = render_all(
        minimal_opord, tmp_path, "mini",
        write_markdown=False, write_html=False, write_pdf=True,
    )
    pdf = outputs["pdf"]
    assert pdf.exists()
    assert pdf.read_bytes()[:5] == b"%PDF-"
    # Minimal should still produce a real document (cover + mission + intent + annex directory).
    assert pdf.stat().st_size > 8_000


# ---------------------------------------------------------------------------
# Annex directory fills A–Z
# ---------------------------------------------------------------------------
def test_annex_status_auto_published_when_content_present():
    a = Annex(letter="B", body="real content")
    assert a.status == AnnexStatus.PUBLISHED


def test_annex_status_auto_omitted_when_empty():
    a = Annex(letter="M")
    assert a.status == AnnexStatus.OMITTED


def test_annex_status_auto_published_when_only_callsigns_set():
    from opord_builder.schema import CallSignEntry, CallSignGroup

    a = Annex(
        letter="H",
        call_sign_groups=[
            CallSignGroup(
                category="BN Main",
                entries=[CallSignEntry(unit="BN CDR", callsign="IRON 6")],
            )
        ],
    )
    assert a.status == AnnexStatus.PUBLISHED


def test_annex_h_frequency_tables_render_in_html(full_opord: OPORD):
    html = render_html(full_opord)
    assert "Battalion Internal Nets" in html
    assert "HOPSET 01" in html
    assert "IRON 6" in html  # callsign in roster
    assert "SAPPER 2" in html
    assert "FALCON 6" in html  # higher HQ callsign
    assert "freq-channel-table" in html


def test_annex_directory_covers_a_through_z(full_opord: OPORD):
    directory = full_opord.annex_directory()
    assert len(directory) == 26
    letters = [a.letter for a in directory]
    assert letters == list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    # Reserved letters are always NOT_USED.
    for letter in "IOTWXY":
        a = next(x for x in directory if x.letter == letter)
        assert a.status == AnnexStatus.NOT_USED


# ---------------------------------------------------------------------------
# YAML !include: mix inline and external annexes in the same file
# ---------------------------------------------------------------------------
def test_include_tag_mixes_inline_and_external_annexes(tmp_path: Path):
    (tmp_path / "annex_b.yaml").write_text(
        "letter: B\n"
        "title: Intelligence\n"
        "body: |\n"
        "  External annex B body.\n",
        encoding="utf-8",
    )
    main = tmp_path / "opord.yaml"
    main.write_text(
        "header:\n"
        "  classification: UNCLASSIFIED\n"
        "  issuing_headquarters: HQ\n"
        "  place_of_issue: X\n"
        "  dtg: 010000ZJAN26\n"
        "  operation_order_number: TEST\n"
        "  operation_name: INCLUDE\n"
        "  time_zone: ZULU\n"
        "mission: Test include.\n"
        "annexes:\n"
        "  - letter: A\n"
        "    body: Inline annex A.\n"
        "  - !include annex_b.yaml\n"
        "  - letter: C\n"
        "    body: Inline annex C.\n",
        encoding="utf-8",
    )
    opord = load_opord(main)
    letters = [a.letter for a in opord.annexes]
    assert letters == ["A", "B", "C"]
    assert opord.annexes[0].body == "Inline annex A."
    assert opord.annexes[1].title == "Intelligence"
    assert "External annex B body." in opord.annexes[1].body
    assert opord.annexes[2].body == "Inline annex C."


def test_include_tag_resolves_paths_relative_to_including_file(tmp_path: Path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.yaml").write_text(
        "letter: A\nbody: Nested include worked.\n", encoding="utf-8"
    )
    main = tmp_path / "opord.yaml"
    main.write_text(
        "header:\n"
        "  classification: UNCLASSIFIED\n"
        "  issuing_headquarters: HQ\n"
        "  place_of_issue: X\n"
        "  dtg: 010000ZJAN26\n"
        "  operation_order_number: T\n"
        "  operation_name: NESTED\n"
        "  time_zone: ZULU\n"
        "mission: Test.\n"
        "annexes:\n"
        "  - !include sub/a.yaml\n",
        encoding="utf-8",
    )
    opord = load_opord(main)
    assert opord.annexes[0].body == "Nested include worked."


def test_variables_block_renders_into_strings(tmp_path: Path):
    """`variables:` at top of YAML is Jinja-rendered into every string value
    and stripped before Pydantic validation."""
    path = tmp_path / "opord.yaml"
    path.write_text(
        "variables:\n"
        "  h_hour: '190500ZAPR26'\n"
        "  op_name: 'IRON STRIKE'\n"
        "  obj_name: 'HAMMER'\n"
        "  phase2:\n"
        "    start: '190500ZAPR26'\n"
        "    end: '190800ZAPR26'\n"
        "header:\n"
        "  classification: UNCLASSIFIED\n"
        "  issuing_headquarters: HQ\n"
        "  place_of_issue: X\n"
        "  dtg: '{{ h_hour }}'\n"
        "  operation_order_number: T\n"
        "  operation_name: '{{ op_name }}'\n"
        "  time_zone: ZULU\n"
        "mission: 'TF attacks NLT {{ h_hour }} to seize OBJ {{ obj_name }} ({{ phase2.start }} to {{ phase2.end }}).'\n"
        "annexes: []\n",
        encoding="utf-8",
    )
    opord = load_opord(path)
    assert opord.header.operation_name == "IRON STRIKE"
    assert opord.header.dtg == "190500ZAPR26"
    assert "OBJ HAMMER" in opord.mission
    assert "190500ZAPR26" in opord.mission
    assert "190800ZAPR26" in opord.mission


def test_variables_undefined_survives_as_literal(tmp_path: Path):
    """Undefined variable names render as literal `{{ name }}` instead of
    raising — authors see the typo in the rendered document."""
    path = tmp_path / "opord.yaml"
    path.write_text(
        "variables:\n"
        "  h_hour: '190500ZAPR26'\n"
        "header:\n"
        "  classification: UNCLASSIFIED\n"
        "  issuing_headquarters: HQ\n"
        "  place_of_issue: X\n"
        "  dtg: '{{ h_hour }}'\n"
        "  operation_order_number: T\n"
        "  operation_name: 'N'\n"
        "  time_zone: ZULU\n"
        "mission: 'Typo here: {{ typo_var }}.'\n",
        encoding="utf-8",
    )
    opord = load_opord(path)
    assert "{{ typo_var }}" in opord.mission
    # HTML render wraps the literal in a styled span for visibility.
    html = render_html(opord)
    assert 'class="undefined-var">{{ typo_var }}</span>' in html


def test_variables_list_values_are_skipped_with_warning(tmp_path: Path):
    """List-valued variables get skipped with a warning — rendering a list
    into a prose field produces ugly repr output so we refuse it."""
    path = tmp_path / "opord.yaml"
    path.write_text(
        "variables:\n"
        "  h_hour: '190500ZAPR26'\n"
        "  bad_list:\n"
        "    - entry1\n"
        "    - entry2\n"
        "header:\n"
        "  classification: UNCLASSIFIED\n"
        "  issuing_headquarters: HQ\n"
        "  place_of_issue: X\n"
        "  dtg: '{{ h_hour }}'\n"
        "  operation_order_number: T\n"
        "  operation_name: 'N'\n"
        "  time_zone: ZULU\n"
        "mission: 'Uses {{ bad_list }} which was dropped.'\n",
        encoding="utf-8",
    )
    with pytest.warns(UserWarning, match="bad_list"):
        opord = load_opord(path)
    # bad_list was sanitized out, so the reference stays as a literal.
    assert "{{ bad_list }}" in opord.mission
    # h_hour still resolves fine.
    assert opord.header.dtg == "190500ZAPR26"


def test_init_scaffold_renders_cleanly(tmp_path: Path):
    """`opord init` output should produce a valid OPORD that renders without errors."""
    from typer.testing import CliRunner

    from opord_builder.cli import app
    from opord_builder.scaffolds import published_letters

    result = CliRunner().invoke(app, ["init", str(tmp_path / "starter")])
    assert result.exit_code == 0, result.output

    root = tmp_path / "starter"
    assert (root / "main.yaml").exists()
    assert (root / "annexes").is_dir()
    for ltr in published_letters():
        assert (root / "annexes" / f"annex_{ltr.lower()}.yaml").exists()

    # The scaffold must load + validate through the real loader (exercises !include).
    opord = load_opord(root / "main.yaml")
    assert len(opord.annexes) == len(published_letters())
    assert opord.annexes[0].letter == "A"

    # --force refusal on re-init without the flag.
    result = CliRunner().invoke(app, ["init", str(root)])
    assert result.exit_code == 1
    assert "Refusing to overwrite" in result.output


def test_frago_loads_and_renders(tmp_path: Path):
    """End-to-end FRAGO flow: load delta YAML + base OPORD, render all three outputs.
    Also exercises schema inheritance (omitted fields fall through to base) and
    `{{ base.* }}` variable interpolation in FRAGO prose."""
    from opord_builder.renderer import load_frago, render_frago_all

    frago_path = REPO / "examples" / "frago_01_iron_strike.yaml"
    assert frago_path.exists()

    frago, base = load_frago(frago_path)
    assert frago.kind == "frago"
    assert frago.frago_number == "01"
    assert base.header.operation_name == "IRON STRIKE"
    # Populated paragraphs
    assert frago.situation is not None
    assert frago.execution is not None
    # Unchanged paragraphs stay None → renderer emits 'No change' stubs
    assert frago.mission is None
    assert frago.sustainment is None
    # Annexes filtered to just B and D
    assert {a.letter for a in frago.annexes} == {"B", "D"}
    # Schema inheritance: these fields were omitted from the FRAGO YAML
    # and should fall through to the base at render time.
    assert frago.classification is None
    assert frago.issuing_headquarters is None
    assert frago.place_of_issue is None
    # `{{ base.header.operation_name }}` interpolation in the FRAGO's
    # execution.coordinating_instructions.other prose resolved to the
    # base operation_name ("IRON STRIKE").
    other = frago.execution.coordinating_instructions.other
    assert "IRON STRIKE" in other
    assert "26-04" in other
    # Flat base-variable pull-through: `{{ h_hour }}` from the base's
    # variables: block resolved in the FRAGO namespace.
    assert "190500ZAPR26" in other
    # Explicit base_vars namespace: `{{ base_vars.bct }}` resolved.
    assert "173d IBCT (A)" in other
    # `{{ base.execution.commanders_intent.end_state }}` pull-through into
    # the FRAGO's enemy situation prose.
    assert frago.situation.enemy_forces is not None
    assert "TF IRON control" in frago.situation.enemy_forces.most_likely_coa
    # `{{ obj_primary }}` flat variable inside annex body.
    annex_b = next(a for a in frago.annexes if a.letter == "B")
    assert "OBJ HAMMER" in annex_b.body

    outputs = render_frago_all(
        frago, base, tmp_path, "frago_01",
        write_markdown=True, write_html=True, write_pdf=True,
    )
    assert outputs["pdf"].exists()
    assert outputs["pdf"].read_bytes()[:5] == b"%PDF-"
    html = outputs["html"].read_text()
    assert "FRAGO 01" in html
    assert "TGT 0045" in html              # new JPITL entry from FRAGO
    assert "No change" in html             # stub for unchanged paragraphs
    assert "IRON STRIKE" in html           # base-order operation name
    # Inherited header fields rendered via `eff.*` fallback.
    assert "2d Battalion" in html          # inherited issuing HQ
    assert "Grafenwoehr" in html           # inherited place of issue


def test_warno_loads_and_renders(tmp_path: Path):
    """End-to-end WARNO flow with base pull-through + standalone mode."""
    from opord_builder.renderer import load_warno, render_warno_all

    # --- With base OPORD ------------------------------------------------
    warno_path = REPO / "examples" / "warno_01_iron_strike.yaml"
    assert warno_path.exists()
    warno, base = load_warno(warno_path)
    assert warno.kind == "warno"
    assert warno.warno_number == "01"
    assert base is not None and base.header.operation_name == "IRON STRIKE"
    # Header inheritance: omitted fields fall through to base.
    assert warno.classification is None
    assert warno.issuing_headquarters is None
    # Populated sections are present.
    assert warno.situation is not None
    assert warno.mission is not None
    assert warno.execution is not None
    # Unset sections stay None → renderer emits TBP stubs.
    assert warno.sustainment is None
    assert warno.command_and_signal is None
    # Coordinating Instructions now carries the doctrinal Para 3.d fields.
    ci = warno.execution.coordinating_instructions
    assert ci is not None
    assert len(ci.time_line) >= 4
    assert ci.earliest_movement_of_forces is not None
    assert "AA PATRIOT" in ci.earliest_movement_of_forces
    assert ci.reconnaissance_and_surveillance_instructions is not None
    assert "Annex L" in ci.reconnaissance_and_surveillance_instructions
    assert ci.orders_group is not None
    assert ci.orders_group.dtg == "181800ZAPR26"
    assert ci.rehearsal is not None
    assert ci.rehearsal.type == "terrain-model"
    # Variable pull-through: {{ h_hour }} flat from base variables.
    assert "190500ZAPR26" in warno.mission
    # Variable pull-through: {{ base.header.operation_name }}.
    assert "IRON STRIKE" in warno.mission
    assert "IRON STRIKE" in warno.execution.commanders_intent.purpose
    # {{ h_hour }} in time_line DTG.
    ld_milestone = next(m for m in ci.time_line if m.event == "LD / H-Hour")
    assert ld_milestone.dtg == "190500ZAPR26"

    outputs = render_warno_all(
        warno, base, tmp_path, "warno_01",
        write_markdown=True, write_html=True, write_pdf=True,
    )
    assert outputs["pdf"].exists()
    assert outputs["pdf"].read_bytes()[:5] == b"%PDF-"
    html = outputs["html"].read_text()
    md = outputs["markdown"].read_text()
    assert "WARNING ORDER" in html
    assert "WARNO 01" in md
    assert "TBP" in html                      # stub for unset sections
    assert "To be published" in md
    assert "IRON STRIKE" in html              # base-order operation name
    assert "2d Battalion" in html             # inherited issuing HQ
    assert "Time Line" in html
    assert "Recon LD" in html
    assert "Orders Group" in html
    assert "Rehearsal" in html
    assert "terrain-model" in html
    # No literal unresolved Jinja placeholders in markdown output.
    assert "{{" not in md

    # --- Standalone WARNO (no base_order) --------------------------------
    standalone_path = REPO / "examples" / "warno_standalone.yaml"
    assert standalone_path.exists()
    w2, b2 = load_warno(standalone_path)
    assert b2 is None
    assert w2.base_order is None
    assert w2.classification is not None  # required when standalone
    assert w2.issuing_headquarters == "Headquarters, 3d Squadron, 2d Cavalry Regiment"
    # Render all three outputs — must not crash on None base.
    outputs2 = render_warno_all(
        w2, None, tmp_path, "warno_standalone",
        write_markdown=True, write_html=True, write_pdf=True,
    )
    assert outputs2["pdf"].read_bytes()[:5] == b"%PDF-"
    md2 = outputs2["markdown"].read_text()
    html2 = outputs2["html"].read_text()
    # Standalone: TBP stubs for unset paragraphs.
    assert "To be published" in md2
    assert "TBP" in html2
    # Higher HQ reference line shows TBP rather than a base citation.
    assert "Higher HQ order" in html2


def test_export_products_all_formats(tmp_path: Path, full_opord: OPORD):
    """`opord export --product {alias-or-path} --format {pdf|html|csv}` should
    produce a standalone file for each known product."""
    from opord_builder.renderer import (
        render_product_csv,
        render_product_html,
        render_product_pdf,
    )

    for product, sentinel in [
        ("jpitl", "TGT 0042"),
        ("tst", "TST-01"),
        ("hptl", "ENY MRC CP"),
        ("cas_9line", "VIPER 11"),          # alias
        ("cap_tracks", "ANCHOR 1"),         # nested airspace path via alias
        ("annex.D.cas_nine_lines", "VIPER 11"),  # raw dotted path
        ("annex.C.airspace_control.cap_tracks", "ANCHOR 1"),  # nested dotted path
    ]:
        csv_text = render_product_csv(full_opord, product)
        assert sentinel in csv_text, f"{sentinel} missing from {product} CSV"
        assert csv_text.splitlines()[0].count(",") >= 3

        html = render_product_html(full_opord, product)
        assert sentinel in html
        assert "class=\"product-cover\"" in html

        slug = product.replace(".", "_")
        pdf_path = tmp_path / f"{slug}.pdf"
        render_product_pdf(full_opord, pdf_path, product)
        assert pdf_path.exists()
        assert pdf_path.read_bytes()[:5] == b"%PDF-"
        assert pdf_path.stat().st_size > 10_000, f"{product} PDF suspiciously small"


def test_export_unknown_path_fails_clearly(full_opord: OPORD):
    from opord_builder.renderer import render_product_csv
    with pytest.raises(ValueError, match="Cannot descend"):
        render_product_csv(full_opord, "annex.D.does_not_exist")


def test_list_products_discovers_seeded_lists(full_opord: OPORD):
    from opord_builder.renderer import discover_products
    products = discover_products(full_opord)
    paths = {path for path, _count, _model in products}
    # Core fires + intel lists we seeded must surface.
    assert "annex.D.jpitl" in paths
    assert "annex.D.time_sensitive_targets" in paths
    assert "annex.D.high_payoff_target_list" in paths
    assert "annex.D.cas_nine_lines" in paths
    assert "annex.B.priority_intelligence_requirements" in paths
    assert "annex.C.airspace_control.cap_tracks" in paths
    assert "execution.tasks_to_subordinate_units" in paths


def test_include_tag_detects_cycles(tmp_path: Path):
    (tmp_path / "a.yaml").write_text(
        "- !include b.yaml\n", encoding="utf-8"
    )
    (tmp_path / "b.yaml").write_text(
        "- !include a.yaml\n", encoding="utf-8"
    )
    main = tmp_path / "opord.yaml"
    main.write_text(
        "header:\n"
        "  classification: UNCLASSIFIED\n"
        "  issuing_headquarters: HQ\n"
        "  place_of_issue: X\n"
        "  dtg: 010000ZJAN26\n"
        "  operation_order_number: T\n"
        "  operation_name: CYCLE\n"
        "  time_zone: ZULU\n"
        "mission: Test.\n"
        "annexes: !include a.yaml\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="cycle"):
        load_opord(main)
