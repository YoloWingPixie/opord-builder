# ruff: noqa: B008
"""`opord import-openaix` and `opord export-openaix`. Registered on the main Typer app by `register`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
import yaml
from pydantic import ValidationError


def _fail(message: str, code: int = 1) -> typer.Exit:
    typer.secho(message, fg=typer.colors.RED, err=True)
    return typer.Exit(code=code)


def _write_json(path: Path, doc: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    typer.echo(f"Wrote {path}  ({path.stat().st_size:,} bytes)")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _fail(f"{path}: invalid JSON: {exc}") from exc


def register(app: typer.Typer) -> None:
    @app.command(
        name="import-openaix",
        help="Convert an OpenAIX opord or frago JSON file to authoring YAML.",
    )
    def import_openaix(
        file: Path = typer.Argument(
            ...,
            exists=True,
            dir_okay=False,
            readable=True,
            help="OpenAIX opord or frago JSON.",
        ),
        out: Path = typer.Option(..., "--out", "-o", help="YAML file to write."),
        resources: Path | None = typer.Option(
            None,
            "--resources",
            help="OpenAIX resources JSON (control measures, channels). Defaults to resources.json beside FILE.",
        ),
        jiptl: Path | None = typer.Option(
            None,
            "--jiptl",
            help="OpenAIX jiptl JSON (Annex D JPITL). Defaults to jiptl.json beside FILE.",
        ),
        base: Path | None = typer.Option(
            None,
            "--base",
            help="For a frago: the base order, as OpenAIX opord JSON or authoring YAML.",
        ),
    ) -> None:
        doc = _load_json(file)
        res_path = resources
        if res_path is None and (file.parent / "resources.json").exists():
            res_path = file.parent / "resources.json"
        res = _load_json(res_path) if res_path else None
        jp_path = jiptl
        if jp_path is None and (file.parent / "jiptl.json").exists():
            jp_path = file.parent / "jiptl.json"
        jp = _load_json(jp_path) if jp_path else None
        kind = doc.get("kind") if isinstance(doc, dict) else None
        try:
            if kind == "opord":
                from opord_builder.openaix.from_openaix import from_openaix

                model, warns = from_openaix(doc, res, jp)
            elif kind == "frago":
                if base is None:
                    raise _fail("a frago needs --base (the base order it changes)", 2)
                model, warns = _import_frago(doc, base, res, jp, out)
            else:
                raise _fail(f"{file}: kind {kind!r} is not an opord or frago", 2)
        except typer.Exit:
            raise
        except (ValueError, ValidationError) as exc:
            raise _fail(f"{file}: {exc}") from exc
        for w in warns:
            typer.secho(f"warning: {w}", fg=typer.colors.YELLOW, err=True)
        data = model.model_dump(mode="json", exclude_unset=True, exclude_none=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100),
            encoding="utf-8",
        )
        typer.echo(f"Wrote {out}  ({out.stat().st_size:,} bytes)")

    @app.command(
        name="export-openaix",
        help="Convert an authoring YAML OPORD or FRAGO to OpenAIX JSON in a directory.",
    )
    def export_openaix(
        file: Path = typer.Argument(
            ..., exists=True, dir_okay=False, readable=True, help="OPORD or FRAGO YAML."
        ),
        out: Path = typer.Option(
            ...,
            "--out",
            "-o",
            help="Directory to write (opord.json or frago.json, resources.json).",
        ),
    ) -> None:
        from opord_builder.openaix.to_openaix import OpenAIXExportError

        try:
            peek = yaml.safe_load(file.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise _fail(f"{file}: invalid YAML: {exc}") from exc
        kind = peek.get("kind") if isinstance(peek, dict) else None
        out.mkdir(parents=True, exist_ok=True)
        try:
            if kind == "frago":
                from opord_builder.openaix.frago import frago_to_openaix
                from opord_builder.renderer import load_frago

                frago, base = load_frago(file)
                fb = frago_to_openaix(frago, base)
                _write_json(out / "frago.json", fb.frago)
                if fb.resources:
                    _write_json(out / "resources.json", fb.resources)
                if fb.jiptl:
                    _write_json(out / "jiptl.json", fb.jiptl)
                warns = fb.warnings
            elif kind in (None, "opord"):
                from opord_builder.openaix.to_openaix import to_openaix
                from opord_builder.renderer import load_opord

                bundle = to_openaix(load_opord(file))
                _write_json(out / "opord.json", bundle.opord)
                if bundle.resources:
                    _write_json(out / "resources.json", bundle.resources)
                if bundle.jiptl:
                    _write_json(out / "jiptl.json", bundle.jiptl)
                warns = bundle.warnings
            else:
                raise _fail(
                    f"{file}: kind {kind!r} cannot be exported (opord or frago only)", 2
                )
        except typer.Exit:
            raise
        except OpenAIXExportError as exc:
            raise _fail(str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise _fail(f"{file}: {exc}") from exc
        for w in warns:
            typer.secho(f"warning: {w}", fg=typer.colors.YELLOW, err=True)


def _import_frago(doc: dict, base: Path, res: dict | None, jp: dict | None, out: Path):
    import os

    from opord_builder.openaix.frago import frago_from_openaix
    from opord_builder.openaix.from_openaix import from_openaix
    from opord_builder.renderer import load_opord

    if base.suffix.lower() == ".json":
        base_model, _ = from_openaix(_load_json(base), None, None)
    else:
        base_model = load_opord(base)
    rel = (
        os.path.relpath(base, out.resolve().parent)
        if base.suffix.lower() != ".json"
        else None
    )
    return frago_from_openaix(doc, base_model, resources=res, jiptl=jp, base_order=rel)
