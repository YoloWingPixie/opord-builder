"""The opord command line."""

from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from opord_builder.cli import app
from opord_builder.load import load_document, read

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
runner = CliRunner()


def run(*args):
    return runner.invoke(app, [str(a) for a in args])


def test_render_writes_the_requested_formats(tmp_path):
    r = run("render", EXAMPLES / "example_minimal.yaml", "-o", tmp_path, "--no-pdf")
    assert r.exit_code == 0, r.output
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "example_minimal.html",
        "example_minimal.md",
    ]
    assert (
        run(
            "render",
            EXAMPLES / "example_minimal.yaml",
            "-o",
            tmp_path,
            "--no-html",
            "--no-md",
            "--no-pdf",
        ).exit_code
        == 0
    )


def test_frago_and_warno_check_the_document_kind(tmp_path):
    assert (
        run(
            "frago", EXAMPLES / "frago_01_iron_strike.yaml", "-o", tmp_path, "--no-pdf"
        ).exit_code
        == 0
    )
    assert (
        run(
            "warno", EXAMPLES / "warno_standalone.yaml", "-o", tmp_path, "--no-pdf"
        ).exit_code
        == 0
    )
    r = run("warno", EXAMPLES / "example_full.yaml", "-o", tmp_path)
    assert r.exit_code == 2 and "not a WARNO" in r.output
    assert run("frago", EXAMPLES / "example_full.yaml", "-o", tmp_path).exit_code == 2


def test_frago_takes_its_base_from_the_option_and_rejects_a_stale_one(tmp_path):
    frago = read(EXAMPLES / "frago_01_iron_strike.yaml")
    del frago["extensions"]["org.opord-builder.order"]["base_order_path"]
    (tmp_path / "f.yaml").write_text(yaml.safe_dump(frago))
    assert run("frago", tmp_path / "f.yaml", "-o", tmp_path, "--no-pdf").exit_code == 2
    assert (
        run(
            "frago",
            tmp_path / "f.yaml",
            "--base",
            EXAMPLES / "example_full.yaml",
            "-o",
            tmp_path,
            "--no-pdf",
        ).exit_code
        == 0
    )
    base = read(EXAMPLES / "example_full.yaml")
    base["meta"]["revision"] = "2"
    (tmp_path / "base.yaml").write_text(yaml.safe_dump(base))
    r = run(
        "frago", tmp_path / "f.yaml", "--base", tmp_path / "base.yaml", "-o", tmp_path
    )
    assert r.exit_code == 2 and "revision" in r.output


def test_export_and_list_products(tmp_path):
    listed = run("list-products", EXAMPLES / "example_full.yaml")
    assert (
        listed.exit_code == 0
        and "jpitl" in listed.output
        and "/execution/tasks_to_subordinate_units" in listed.output
    )
    out = tmp_path / "j.csv"
    assert (
        run(
            "export",
            EXAMPLES / "example_full.yaml",
            "-p",
            "jpitl",
            "-f",
            "csv",
            "-o",
            out,
        ).exit_code
        == 0
    )
    assert out.read_text().startswith("approval_authority")
    assert (
        run(
            "export",
            EXAMPLES / "example_full.yaml",
            "-p",
            "/execution/nothing",
            "-f",
            "csv",
            "-o",
            out,
        ).exit_code
        == 2
    )


def test_init_writes_a_valid_order_and_refuses_to_overwrite(tmp_path):
    assert run("init", tmp_path / "o").exit_code == 0
    assert load_document(tmp_path / "o" / "opord.yaml")["kind"] == "opord"
    assert (
        run(
            "render", tmp_path / "o" / "opord.yaml", "-o", tmp_path, "--no-pdf"
        ).exit_code
        == 0
    )
    again = run("init", tmp_path / "o")
    assert again.exit_code == 1 and "Refusing" in again.output
    assert run("init", tmp_path / "o", "--force").exit_code == 0


def test_validate_openaix_reports_pointers(tmp_path):
    assert run("validate-openaix", EXAMPLES / "example_full.yaml").exit_code == 0
    doc = read(EXAMPLES / "example_full.yaml")
    doc["extensions"]["org.opord-builder.order"]["situation"]["area_of_interest"] = 3
    (tmp_path / "bad.yaml").write_text(yaml.safe_dump(doc))
    r = run("validate-openaix", tmp_path / "bad.yaml")
    assert (
        r.exit_code == 1
        and "/extensions/org.opord-builder.order/situation/area_of_interest" in r.output
    )


def test_a_bad_document_is_reported_with_exit_code_2(tmp_path):
    (tmp_path / "x.yaml").write_text("kind: opord\n")
    r = run("render", tmp_path / "x.yaml", "-o", tmp_path)
    assert r.exit_code == 2


ATO = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "openaix"
    / "atomic-thunder"
    / "ato.json"
)


def test_kneeboard_from_an_ato_and_its_options(tmp_path):
    r = run("kneeboard", "--ato", ATO, "--flight", "viper-1", "-o", tmp_path)
    assert r.exit_code == 0, r.output
    assert list(tmp_path.glob("ato_kneeboard_*"))
    assert run("kneeboard").exit_code == 2
    assert run("kneeboard", "--flight", "viper-1").exit_code == 2
    nope = run("kneeboard", "--ato", ATO, "--flight", "nope", "-o", tmp_path)
    assert nope.exit_code == 2 and "no flight 'nope'" in nope.output


def test_kneeboard_cards_override_the_ato_in_an_order(tmp_path):
    doc = read(EXAMPLES / "example_minimal.yaml")
    doc["extensions"]["org.opord-builder.kneeboard"] = {
        "cards": [{"flight_callsign": "VIPER1", "weaponeering": "Other load"}]
    }
    (tmp_path / "opord.yaml").write_text(yaml.safe_dump(doc))
    r = run("kneeboard", tmp_path / "opord.yaml", "--ato", ATO, "-o", tmp_path / "png")
    assert r.exit_code == 0, r.output
    assert "weaponeering: YAML value 'Other load' overrides ATO value" in r.output
