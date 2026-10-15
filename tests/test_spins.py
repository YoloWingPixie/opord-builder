from copy import deepcopy

import pytest
from pydantic import ValidationError

from opord_builder.schema.spins import SPINS
from opord_builder.spins import compose_spins, render_spins_html


def document(content=None, **extra):
    return {
        "kind": "spins",
        "schema_version": "0.3",
        "meta": {"id": "standing", "title": "Training SPINS", "revision": "3"},
        "scope": "standing",
        "content": content
        if content is not None
        else [
            {
                "kind": "paragraph",
                "id": "opening",
                "text": "Opening instructions.",
            }
        ],
        **extra,
    }


def test_numbered_nested_prose_and_references():
    nested = {
        "kind": "paragraph",
        "id": "deep",
        "text": "Deep instruction.",
    }
    for depth in reversed(range(6)):
        nested = {
            "kind": "section",
            "id": f"section-{depth}",
            "title": f"Level {depth}",
            "blocks": [nested],
        }
    data = document([nested, {"kind": "paragraph", "text": [{"target": "deep"}]}])
    html = render_spins_html(SPINS.model_validate(data))
    assert ">Paragraph 1.1.1.1.1.1.1</a>" in html
    assert 'href="#node-deep"' in html
    assert html.index("Level 0") < html.index("Deep instruction.")


@pytest.mark.parametrize(
    "content",
    [
        [
            {"kind": "paragraph", "id": "same", "text": "A"},
            {"kind": "note", "id": "same", "text": "B"},
        ],
        [{"kind": "paragraph", "text": [{"target": "missing"}]}],
    ],
)
def test_invalid_reference_identity_is_rejected(content):
    with pytest.raises(ValidationError):
        SPINS.model_validate(document(content))


def test_amendments_renumber_references_without_mutating_baseline():
    baseline = SPINS.model_validate(
        document(
            [
                {
                    "kind": "section",
                    "id": "airspace",
                    "title": "Airspace",
                    "blocks": [
                        {
                            "kind": "paragraph",
                            "id": "a",
                            "text": "First",
                        },
                        {
                            "kind": "paragraph",
                            "id": "b",
                            "text": "Third",
                        },
                        {"kind": "paragraph", "text": [{"target": "b"}]},
                    ],
                },
            ]
        )
    )
    overlay = SPINS.model_validate(
        document(
            [],
            scope="mission",
            period={"start": "2026-09-18T20:00:00Z", "end": "2026-09-18T23:00:00Z"},
            base={"id": "standing", "revision": "3", "path": "standing.yaml"},
            changes=[
                {
                    "op": "replace",
                    "target": "a",
                    "block": {
                        "kind": "paragraph",
                        "id": "a",
                        "text": "Updated",
                    },
                },
                {
                    "op": "add",
                    "parent": "airspace",
                    "before": "b",
                    "block": {"kind": "paragraph", "text": "Inserted"},
                },
            ],
        )
    )
    before = deepcopy(baseline.model_dump())
    effective = compose_spins(baseline, overlay)
    assert baseline.model_dump() == before
    assert effective.content[0].blocks[0].text == "Updated"
    assert ">Paragraph 1.2</a>" in render_spins_html(baseline)
    assert ">Paragraph 1.3</a>" in render_spins_html(effective)


def test_ordered_blocks_share_automatic_numbering_across_formats():
    from opord_builder.spins import render_spins_markdown

    data = document(
        [
            {
                "kind": "section",
                "role": "part",
                "title": "Standing",
                "blocks": [
                    {
                        "kind": "section",
                        "title": "Airspace",
                        "blocks": [
                            {
                                "kind": "paragraph",
                                "id": "entry",
                                "text": "Request entry.",
                            },
                            {
                                "kind": "table",
                                "id": "channels",
                                "caption": "Channels",
                                "columns": [{"key": "agency", "heading": "Agency"}],
                                "rows": [{"agency": "MAGIC"}],
                            },
                            {
                                "kind": "paragraph",
                                "id": "exit",
                                "text": "Report clear.",
                            },
                            {
                                "kind": "list",
                                "style": "lower_alpha",
                                "items": [
                                    {
                                        "text": "Read back",
                                        "blocks": [
                                            {
                                                "kind": "paragraph",
                                                "id": "nested-list",
                                                "text": "Confirm.",
                                            }
                                        ],
                                    }
                                ],
                            },
                        ],
                    },
                ],
            },
            {
                "kind": "section",
                "role": "annex",
                "title": "Recovery",
                "blocks": [
                    {
                        "kind": "section",
                        "role": "appendix",
                        "title": "Reports",
                        "blocks": [
                            {
                                "kind": "paragraph",
                                "id": "report",
                                "text": "Report status.",
                            },
                        ],
                    },
                ],
            },
            {
                "kind": "paragraph",
                "text": [
                    {"target": "exit"},
                    {"text": "; "},
                    {"target": "channels"},
                    {"text": "; "},
                    {"target": "report"},
                    {"text": "; "},
                    {"target": "nested-list"},
                ],
            },
        ]
    )
    model = SPINS.model_validate(data)
    html = render_spins_html(model)
    md = render_spins_markdown(model)
    for output in (html, md):
        assert "Part I, Paragraph 1.2" in output
        assert "Annex A, Appendix 1, Paragraph 1" in output
        assert "Part I, Paragraph 1.3.1.1" in output
        assert "Table 1" in output
        assert '<ol type="a" start="1">' in output
        assert (
            output.index("Request entry.")
            < output.index("Channels")
            < output.index("Report clear.")
        )
    assert "| Agency |\n| :--- |\n| MAGIC |" in md
    assert model.model_dump() == SPINS.model_validate(data).model_dump()


def test_reordering_updates_contents_and_reference_numbers():
    from opord_builder.spins import render_spins_markdown

    sections = [
        {
            "kind": "section",
            "id": name,
            "title": name.title(),
            "blocks": [{"kind": "paragraph", "text": "Instructions"}],
        }
        for name in ("airspace", "airfields")
    ]
    link = {"kind": "paragraph", "text": [{"target": "airfields"}]}
    original = SPINS.model_validate(document([*sections, link]))
    reordered = SPINS.model_validate(document([*reversed(sections), link]))
    assert ">2 Airfields</a>" in render_spins_html(original)
    assert ">1 Airfields</a>" in render_spins_html(reordered)
    assert "[Section 2](#node-airfields)" in render_spins_markdown(original)
    assert "[Section 1](#node-airfields)" in render_spins_markdown(reordered)


def test_emphasis_citations_and_literal_text_are_preserved():
    from opord_builder.spins import render_spins_markdown

    data = document(
        [
            {
                "kind": "paragraph",
                "lead": [{"text": "Check-in", "marks": ["underline"]}],
                "text": [
                    {"text": '<script>& "literal"', "marks": ["bold", "italic"]},
                    {"text": " see "},
                    {"citation": "brief"},
                    {"text": " and "},
                    {"text": "<code>", "marks": ["code"]},
                ],
            },
            {"kind": "reference", "reference": "brief"},
        ]
    )
    data["meta"]["references"] = [
        {"id": "brief", "title": "Briefing <notes>", "url": "https://example.org/brief"}
    ]
    model = SPINS.model_validate(data)
    html = render_spins_html(model)
    assert "<u>Check-in</u>" in html
    assert (
        "<em><strong>&lt;script&gt;&amp; &quot;literal&quot;</strong></em> see " in html
    )
    assert 'href="#citation-brief">Reference 1</a>' in html
    assert "<code>&lt;code&gt;</code>" in html
    assert "Reference 1: Briefing &lt;notes&gt;" in html
    assert "<script>" not in html
    assert "[Reference 1](#citation-brief)" in render_spins_markdown(model)


@pytest.mark.parametrize(
    "style,marker",
    [
        ("decimal", "1"),
        ("lower_alpha", "a"),
        ("upper_alpha", "A"),
        ("lower_roman", "i"),
        ("upper_roman", "I"),
    ],
)
def test_list_style_is_preserved_in_both_formats(style, marker):
    from opord_builder.spins import render_spins_markdown

    model = SPINS.model_validate(
        document(
            [
                {
                    "kind": "list",
                    "style": style,
                    "start": 3,
                    "items": [{"text": "<literal>"}],
                }
            ]
        )
    )
    for output in (render_spins_html(model), render_spins_markdown(model)):
        assert f'<ol type="{marker}" start="3">' in output
        assert "&lt;literal&gt;" in output
        assert "<literal>" not in output


@pytest.mark.parametrize(
    "changes,error",
    [
        ([{"op": "remove", "target": "missing"}], "unknown amendment target"),
        (
            [
                {
                    "op": "replace",
                    "target": "opening",
                    "block": {
                        "kind": "paragraph",
                        "id": "different",
                        "text": "Changed",
                    },
                }
            ],
            "retain its target",
        ),
        (
            [
                {"op": "remove", "target": "opening"},
                {"op": "remove", "target": "opening"},
            ],
            "overlapping",
        ),
        (
            [
                {
                    "op": "add",
                    "parent": "missing",
                    "block": {"kind": "paragraph", "text": "New"},
                }
            ],
            "unknown amendment parent",
        ),
        (
            [
                {
                    "op": "add",
                    "after": "missing",
                    "block": {"kind": "paragraph", "text": "New"},
                }
            ],
            "not a sibling",
        ),
    ],
)
def test_conflicting_amendments_fail_with_specific_errors(changes, error):
    baseline = SPINS.model_validate(document())
    with pytest.raises(ValueError, match=error):
        compose_spins(baseline, mission(changes))


def mission(changes, **extra):
    return SPINS.model_validate(
        document(
            [],
            scope="mission",
            period={"start": "2026-09-18T20:00:00Z", "end": "2026-09-18T23:00:00Z"},
            base={"id": "standing", "revision": "3", "path": "standing.yaml"},
            changes=changes,
            **extra,
        )
    )


def test_add_remove_and_references_validate_the_effective_document():
    baseline = SPINS.model_validate(
        document(
            [
                {"kind": "paragraph", "id": "keep", "text": "Keep"},
                {"kind": "paragraph", "id": "obsolete", "text": "Obsolete"},
                {"kind": "paragraph", "id": "last", "text": [{"target": "keep"}]},
            ]
        )
    )
    amendment = mission(
        [
            {
                "op": "add",
                "after": "keep",
                "block": {"kind": "paragraph", "text": "Added first"},
            },
            {
                "op": "add",
                "after": "keep",
                "block": {"kind": "paragraph", "text": "Added second"},
            },
            {"op": "remove", "target": "obsolete"},
        ]
    )
    original = deepcopy(amendment.model_dump())
    effective = compose_spins(baseline, amendment)
    assert [block.text for block in effective.content[:3]] == [
        "Keep",
        "Added first",
        "Added second",
    ]
    assert amendment.model_dump() == original
    assert "Obsolete" not in render_spins_html(effective)
    with pytest.raises(ValidationError, match="unresolved block reference"):
        compose_spins(baseline, mission([{"op": "remove", "target": "keep"}]))
    wrong_revision = baseline.model_copy(deep=True)
    wrong_revision.meta.revision = "4"
    with pytest.raises(ValueError, match="pinned reference"):
        compose_spins(wrong_revision, amendment)


@pytest.mark.parametrize(
    "content,error",
    [
        ([{"kind": "paragraph", "label": "1.1", "text": "Manual"}], "Extra inputs"),
        ([{"kind": "paragraph", "text": "   "}], "cannot be blank"),
        ([{"kind": "note", "text": [{"citation": "missing"}]}], "unresolved citation"),
        (
            [
                {
                    "kind": "table",
                    "caption": "Table",
                    "columns": [{"key": "a", "heading": "A"}],
                    "rows": [{"b": "Wrong"}],
                }
            ],
            "expected cells",
        ),
        (
            [
                {
                    "kind": "table",
                    "caption": "Table",
                    "columns": [
                        {"key": "a", "heading": "A"},
                        {"key": "a", "heading": "Again"},
                    ],
                    "rows": [{"a": "A"}],
                }
            ],
            "column keys must be unique",
        ),
        (
            [
                {
                    "kind": "table",
                    "caption": "Table",
                    "columns": [{"key": "a", "heading": "A"}],
                    "rows": [{"a": [{"target": "missing"}]}],
                }
            ],
            "unresolved block reference",
        ),
    ],
)
def test_invalid_publication_contracts(content, error):
    with pytest.raises(ValidationError, match=error):
        SPINS.model_validate(document(content))


def test_mission_requires_an_ordered_timezone_aware_period():
    with pytest.raises(ValidationError, match="effective period"):
        SPINS.model_validate(document(scope="mission"))
    for period in [
        {"start": "2026-09-18T20:00:00", "end": "2026-09-18T23:00:00Z"},
        {"start": "2026-09-18T23:00:00Z", "end": "2026-09-18T20:00:00Z"},
    ]:
        with pytest.raises(ValidationError):
            SPINS.model_validate(document(scope="mission", period=period))


def test_source_tables_use_the_canonical_registry(tmp_path):
    from pathlib import Path

    import yaml

    from opord_builder.spins import load_spins

    source_path = (
        Path(__file__).resolve().parents[1]
        / "examples/data_sources/airspace/cap_tracks.yaml"
    )
    block = {
        "kind": "source_table",
        "caption": "Stations",
        "source": str(source_path),
        "columns": [{"key": "name", "heading": "Station", "field": "name"}],
    }
    path = tmp_path / "spins.yaml"
    path.write_text(yaml.safe_dump(document([block])))
    assert "ANCHOR 1" in render_spins_html(load_spins(path))
    block["columns"][0]["field"] = "unknown"
    path.write_text(yaml.safe_dump(document([block])))
    with pytest.raises(ValueError, match="unknown field 'unknown'"):
        load_spins(path)


def test_figures_resolve_from_each_owning_document_and_are_renumbered(tmp_path):
    import base64

    import yaml

    from opord_builder.spins import load_spins

    standing_dir = tmp_path / "standing"
    standing_dir.mkdir()
    standing_image = (
        '<svg xmlns="http://www.w3.org/2000/svg"><text>Standing image</text></svg>'
    )
    mission_image = (
        '<svg xmlns="http://www.w3.org/2000/svg"><text>Mission image</text></svg>'
    )
    (standing_dir / "map.svg").write_text(standing_image)
    (tmp_path / "map.svg").write_text(mission_image)
    figure = {
        "kind": "figure",
        "id": "map",
        "caption": "Map",
        "alt": "Map",
        "src": "map.svg",
    }
    (standing_dir / "standing.yaml").write_text(yaml.safe_dump(document([figure])))
    new_figure = {**figure, "id": "mission-map"}
    overlay = mission([{"op": "add", "before": "map", "block": new_figure}])
    overlay.base.path = "standing/standing.yaml"
    data = overlay.model_dump(mode="json")
    data["content"] = [{"kind": "paragraph", "text": [{"target": "map"}]}]
    (tmp_path / "mission.yaml").write_text(yaml.safe_dump(data))
    html = render_spins_html(load_spins(tmp_path / "mission.yaml"))
    assert (
        "data:image/svg+xml;base64,"
        + base64.b64encode(standing_image.encode()).decode()
        in html
    )
    assert (
        "data:image/svg+xml;base64," + base64.b64encode(mission_image.encode()).decode()
        in html
    )
    assert ">Figure 2</a>" in html
    assert "<link " not in html
    assert 'src="http' not in html


def test_cli_schema_rendering_and_validation(tmp_path):
    import json
    from pathlib import Path

    from typer.testing import CliRunner

    from opord_builder.cli import app

    runner = CliRunner()
    schema_result = runner.invoke(app, ["schema", "--document-type", "spins"])
    assert schema_result.exit_code == 0, schema_result.output
    exported = json.loads(schema_result.output)
    assert exported["properties"]["kind"]["const"] == "spins"
    assert "label" not in exported["$defs"]["Paragraph"]["properties"]
    example = Path(__file__).resolve().parents[1] / "examples/spins-example.yaml"
    result = runner.invoke(
        app, ["spins", str(example), "-o", str(tmp_path), "--no-pdf"]
    )
    assert result.exit_code == 0, result.output
    html = (tmp_path / "spins-example.html").read_text()
    assert ">Part III, Paragraph 2.1</a>" in html
    assert "ANCHOR 1" in html
    assert (tmp_path / "spins-example.md").exists()
    assert not (tmp_path / "spins-example.pdf").exists()
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("kind: spins\ncontent: [")
    failure = runner.invoke(app, ["spins", str(invalid)])
    assert failure.exit_code == 2
    assert str(invalid) in failure.output


def test_pdf_contains_generated_numbers_headers_and_page_counts(tmp_path):
    from pathlib import Path

    import pypdfium2 as pdfium

    from opord_builder.spins import load_spins, render_spins_pdf

    example = Path(__file__).resolve().parents[1] / "examples/spins-example.yaml"
    model = load_spins(example)
    model.meta.handling = "TRAINING PUBLICATION"
    path = render_spins_pdf(model, tmp_path / "spins.pdf")
    pdf = pdfium.PdfDocument(path)
    try:
        pages = []
        for index in range(len(pdf)):
            page = pdf[index]
            text_page = page.get_textpage()
            try:
                pages.append(text_page.get_text_range())
            finally:
                text_page.close()
                page.close()
        assert len(pages) > 1
        for number, text in enumerate(pages, 1):
            assert "TRAINING PUBLICATION" in text
            assert f"{number} / {len(pages)}" in text
            assert "training-session" in text
        assert "Part III, Paragraph 2.1" in "\n".join(pages)
    finally:
        pdf.close()


def test_mission_inherits_presentation_and_overrides_only_authored_fields():
    baseline = SPINS.model_validate(
        document(
            presentation={
                "font": "monospace",
                "text_case": "uppercase",
                "page_size": "Letter",
            }
        )
    )
    baseline.meta.classification = None
    baseline.meta.handling = "EXERCISE"
    amendment = mission([], presentation={"contents": False})
    effective = compose_spins(baseline, amendment)
    assert effective.presentation.font == "monospace"
    assert effective.presentation.page_size == "Letter"
    assert effective.presentation.contents is False
    html = render_spins_html(effective)
    assert "OPENING INSTRUCTIONS." in html
    assert "EXERCISE" in html
    assert 'class="publication-contents"' not in html


def test_includes_and_variables_feed_spins_prose(tmp_path):
    from opord_builder.spins import load_spins

    (tmp_path / "instructions.yaml").write_text(
        '- kind: paragraph\n  text: "Contact {{ control }}."\n'
    )
    path = tmp_path / "spins.yaml"
    path.write_text(
        "kind: spins\nschema_version: '0.3'\nscope: standing\nmeta: {id: example, title: Instructions, revision: '1'}\nvariables: {control: MAGIC}\ncontent: !include instructions.yaml\n"
    )
    assert "Contact MAGIC." in render_spins_html(load_spins(path))


def test_added_identity_cannot_redirect_a_later_amendment():
    baseline = SPINS.model_validate(document())
    amendment = mission(
        [
            {
                "op": "add",
                "after": "opening",
                "block": {
                    "kind": "paragraph",
                    "id": "opening",
                    "text": "Duplicate identity",
                },
            },
            {"op": "remove", "target": "opening"},
        ]
    )
    with pytest.raises(ValueError, match="identifiers conflict"):
        compose_spins(baseline, amendment)
