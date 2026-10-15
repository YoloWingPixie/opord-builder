"""The committed authoring schemas must match what Pydantic generates."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from opord_builder.cli import DEFAULT_SCHEMA_PATHS, app

ROOT = Path(__file__).resolve().parent.parent
runner = CliRunner()


@pytest.mark.parametrize("doc_type", ["opord", "spins"])
def test_committed_schema_is_fresh(doc_type, monkeypatch):
    monkeypatch.chdir(ROOT)
    result = runner.invoke(app, ["schema", "--document-type", doc_type, "--check"])
    assert result.exit_code == 0, result.output


def test_check_fails_on_stale_schema(tmp_path):
    stale = tmp_path / "stale.schema.json"
    stale.write_text("{}\n", encoding="utf-8")
    result = runner.invoke(app, ["schema", "--check", "--out", str(stale)])
    assert result.exit_code == 1
    assert "stale" in result.output


def test_check_fails_on_missing_schema(tmp_path):
    result = runner.invoke(
        app, ["schema", "--check", "--out", str(tmp_path / "x.json")]
    )
    assert result.exit_code == 1


def test_default_paths_exist():
    for path in DEFAULT_SCHEMA_PATHS.values():
        assert (ROOT / path).exists()
    assert not (ROOT / "schemas" / "opord.schema.json").exists()
