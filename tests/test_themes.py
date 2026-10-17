"""Named document themes: selection (flag, YAML, unknown, default) and a render smoke test of wp90 per command."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from opord_builder import render, themes
from opord_builder.cli import app
from opord_builder.load import read
from opord_builder.order import load_order
from opord_builder.spins import load_spins, render_spins_html

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
runner = CliRunner()


def run(*args):
    return runner.invoke(app, [str(a) for a in args])


def themed_copy(src: Path, dest: Path, ns: str, name: str) -> Path:
    """A copy of an example, with `theme: name` in its `org.opord-builder.<ns>` extension."""
    doc = read(src)
    doc["extensions"][f"org.opord-builder.{ns}"]["theme"] = name
    dest.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return dest


# --------------------------------------------------------------------------- selection


def test_wp90_is_available():
    assert "wp90" in themes.available()


def test_the_flag_wins_over_the_document_and_the_default_is_no_theme():
    assert themes.resolve(None, None) is None
    assert themes.resolve(None, "wp90") == "wp90"
    assert themes.resolve("wp90", None) == "wp90"
    assert themes.resolve("wp90", "nonesuch") == "wp90"


def test_an_unknown_theme_names_the_available_ones():
    with pytest.raises(ValueError, match=r"unknown theme 'nonesuch'.*wp90"):
        themes.resolve("nonesuch")
    with pytest.raises(ValueError, match=r"unknown theme 'nonesuch'.*wp90"):
        themes.resolve(None, "nonesuch")


def test_the_default_output_carries_no_theme():
    o = load_order(EXAMPLES / "example_minimal.yaml")
    html = render.render_html(o)
    assert html == render.render_html(o, None)
    assert "theme-wp90" not in html and "doc-seal" not in html
    assert (
        "<style" in html and html.count("<style") == 2
    )  # page rules + base stylesheet


def test_a_theme_is_layered_after_the_base_stylesheet():
    html = render.render_html(load_order(EXAMPLES / "example_minimal.yaml"), "wp90")
    assert html.index("OPORD — Swiss") < html.index("wp90 - an early-1990s")
    assert 'class="doc-seal"' in html and "theme-wp90" in html


def test_the_document_names_its_theme(tmp_path):
    src = themed_copy(
        EXAMPLES / "example_minimal.yaml", tmp_path / "o.yaml", "order", "wp90"
    )
    assert "theme-wp90" in render.render_html(load_order(src))
    # the flag wins over the document
    r = run("render", src, "-o", tmp_path / "out", "--no-pdf", "--theme", "wp90")
    assert r.exit_code == 0, r.output


def test_an_unknown_document_theme_fails_with_the_list(tmp_path):
    src = themed_copy(
        EXAMPLES / "example_minimal.yaml", tmp_path / "o.yaml", "order", "nonesuch"
    )
    r = run("render", src, "-o", tmp_path / "out", "--no-pdf")
    assert r.exit_code == 2 and "nonesuch" in r.output and "wp90" in r.output
    assert not (tmp_path / "out").exists()


def test_an_unknown_flag_fails_for_every_command(tmp_path):
    out = tmp_path / "out"
    for args in (
        ("render", EXAMPLES / "example_minimal.yaml"),
        ("frago", EXAMPLES / "frago_01_iron_strike.yaml"),
        ("warno", EXAMPLES / "warno_standalone.yaml"),
        ("spins", EXAMPLES / "spins-standing.yaml"),
        ("export", EXAMPLES / "example_full.yaml", "-p", "jpitl", "-f", "html"),
    ):
        r = run(*args, "-o", out, "--theme", "nonesuch")
        assert r.exit_code == 2, args
        assert "unknown theme 'nonesuch'" in r.output and "wp90" in r.output, args


def test_the_spins_document_names_its_theme(tmp_path):
    for name in ("data_sources", "assets"):
        (tmp_path / name).symlink_to(EXAMPLES / name)
    src = themed_copy(
        EXAMPLES / "spins-standing.yaml", tmp_path / "s.yaml", "spins", "wp90"
    )
    assert "theme-wp90" in render_spins_html(load_spins(src))
    assert "theme-" not in render_spins_html(
        load_spins(EXAMPLES / "spins-standing.yaml")
    )


# --------------------------------------------------------------------------- smoke: wp90 on every render command


@pytest.mark.parametrize(
    ("command", "example"),
    [
        ("render", "example_minimal"),
        ("frago", "frago_01_iron_strike"),
        ("warno", "warno_standalone"),
        ("spins", "spins-standing"),
    ],
)
def test_wp90_renders_each_command(command, example, tmp_path):
    r = run(command, EXAMPLES / f"{example}.yaml", "-o", tmp_path, "--theme", "wp90")
    assert r.exit_code == 0, r.output
    html = (tmp_path / f"{example}.html").read_text(encoding="utf-8")
    assert "theme-wp90" in html and "doc-seal" in html
    assert (tmp_path / f"{example}.pdf").read_bytes().startswith(b"%PDF")
    page = first_page(html, render.pdf_stylesheet("wp90"))
    assert (page.width, page.height) == (816, 1056)  # US Letter in CSS px


def first_page(html, stylesheet):
    from weasyprint import HTML

    return HTML(string=html).render(stylesheets=[stylesheet]).pages[0]


def test_wp90_exports_a_product(tmp_path):
    for fmt in ("html", "pdf"):
        out = tmp_path / f"j.{fmt}"
        r = run(
            "export", EXAMPLES / "example_full.yaml", "-p", "jpitl",
            "-f", fmt, "-o", out, "--theme", "wp90",
        )  # fmt: skip
        assert r.exit_code == 0, r.output
    assert "theme-wp90" in (tmp_path / "j.html").read_text(encoding="utf-8")
    assert (tmp_path / "j.pdf").read_bytes().startswith(b"%PDF")


def test_wp90_forces_light_and_hides_the_theme_toggle():
    css = themes.css("wp90")
    assert "color-scheme: light" in css and ".theme-toggle { display: none; }" in css
    assert "border-radius: 0" in css and "box-shadow: none" in css
