"""`opord` CLI entry point."""

from __future__ import annotations

import json
import sys
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
import yaml
from pydantic import ValidationError

from opord_builder.renderer import (
    discover_products,
    load_frago,
    load_opord,
    load_warno,
    render_all,
    render_frago_all,
    render_warno_all,
    render_kneeboards,
    render_product_csv,
    render_product_html,
    render_product_pdf,
    _inline_stylesheet,
    _load_yaml_with_variables,
    _PRODUCT_ALIASES,
)
from opord_builder.schema import OPORD
from opord_builder.schema.data_sources import DATA_SOURCE_REGISTRY


class SchemaFormat(str, Enum):
    JSON = "json"
    YAML = "yaml"


class ExportFormat(str, Enum):
    PDF = "pdf"
    HTML = "html"
    CSV = "csv"


def _echo_wrote(label: str, path: Path) -> None:
    typer.secho(
        f"Wrote {label} → {path}  ({path.stat().st_size:,} bytes)",
        fg=typer.colors.GREEN,
    )

app = typer.Typer(
    name="opord",
    add_completion=False,
    help="Render a YAML OPORD definition into Markdown and a drippy PDF.",
    no_args_is_help=True,
)


def _build_schema_dict(
    model: type, slug: str, title: str, description: str,
) -> dict:
    schema_dict = model.model_json_schema()
    schema_dict["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema_dict["$id"] = (
        f"https://github.com/opord-builder/opord-builder/schemas/{slug}.schema.json"
    )
    schema_dict.setdefault("title", title)
    schema_dict.setdefault("description", description)
    return schema_dict


def _build_opord_schema_dict() -> dict:
    return _build_schema_dict(
        OPORD, "opord", "OPORD",
        "U.S. Army Operations Order per FM 6-0 (May 2022) Appendix D / ATP 5-0.2-1.",
    )


def _fmt_validation_error(exc: ValidationError, yaml_path: Path) -> str:
    lines = [f"Schema validation failed for {yaml_path}:"]
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        lines.append(f"  - {loc}: {err['msg']}")
    return "\n".join(lines)


@app.command(help="Render an OPORD YAML file to Markdown and PDF.")
def render(
    input_file: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to the OPORD YAML file.",
    ),
    out_dir: Optional[Path] = typer.Option(
        None,
        "--out-dir",
        "-o",
        help="Output directory. Defaults to ./output/.",
    ),
    md: bool = typer.Option(True, "--md/--no-md", help="Write a Markdown file."),
    html: bool = typer.Option(True, "--html/--no-html", help="Write a standalone HTML file."),
    pdf: bool = typer.Option(True, "--pdf/--no-pdf", help="Write a PDF file."),
) -> None:
    try:
        opord = load_opord(input_file)
    except ValidationError as exc:
        typer.secho(_fmt_validation_error(exc, input_file), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    target_dir = out_dir or Path("output")
    stem = input_file.stem
    outputs = render_all(
        opord, target_dir, stem, write_markdown=md, write_html=html, write_pdf=pdf
    )

    typer.secho(
        f"Rendered {input_file.name}  →  "
        + ", ".join(p.name for p in outputs.values()),
        fg=typer.colors.GREEN,
    )
    for kind, path in outputs.items():
        size = path.stat().st_size
        typer.echo(f"  {kind:<8}  {path}  ({size:,} bytes)")


@app.command(name="validate-source", help="Validate a standalone data-source YAML file.")
def validate_source(
    input_file: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to the data-source YAML file.",
    ),
) -> None:
    data, _ = _load_yaml_with_variables(input_file)

    if not isinstance(data, dict) or "kind" not in data:
        typer.secho(
            f"File {input_file} is not a valid data-source document "
            f"(missing top-level 'kind' field).",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    kind = data["kind"]
    model = DATA_SOURCE_REGISTRY.get(kind)
    if model is None:
        known = ", ".join(sorted(DATA_SOURCE_REGISTRY))
        typer.secho(
            f"Unknown data-source kind '{kind}'. Known kinds: {known}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    try:
        doc = model.model_validate(data)
    except ValidationError as exc:
        typer.secho(_fmt_validation_error(exc, input_file), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    entries = getattr(doc, "entries", [])
    typer.secho(
        f"✓ Valid {kind} data source: {input_file.name} ({len(entries)} entries)",
        fg=typer.colors.GREEN,
    )


def _build_data_source_schema_dict(kind: str) -> dict:
    return _build_schema_dict(
        DATA_SOURCE_REGISTRY[kind], kind, kind.upper(),
        f"Standalone {kind.upper()} data-source document.",
    )


@app.command(help="Emit the OPORD JSON Schema (Draft 2020-12).")
def schema(
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        "-o",
        help="Write to this file instead of stdout.",
    ),
    fmt: SchemaFormat = typer.Option(
        SchemaFormat.JSON,
        "--format",
        "-f",
        help="Output format.",
    ),
    source_type: Optional[str] = typer.Option(
        None,
        "--source-type",
        "-s",
        help="Emit schema for a data-source type instead of OPORD (e.g. jpitl, tst, hpt, all).",
    ),
) -> None:
    # --- data-source schema mode ------------------------------------------
    if source_type is not None:
        if source_type == "all":
            kinds = sorted(DATA_SOURCE_REGISTRY)
        elif source_type in DATA_SOURCE_REGISTRY:
            kinds = [source_type]
        else:
            known = ", ".join(sorted(DATA_SOURCE_REGISTRY))
            typer.secho(
                f"Unknown source type '{source_type}'. Known types: {known}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2)

        for kind in kinds:
            schema_dict = _build_data_source_schema_dict(kind)

            if fmt is SchemaFormat.YAML:
                text = yaml.safe_dump(schema_dict, sort_keys=False, width=100)
            else:
                text = json.dumps(schema_dict, indent=2, ensure_ascii=False) + "\n"

            if out:
                # When writing multiple kinds, treat --out as a directory.
                if len(kinds) > 1:
                    out_dir = out
                    out_dir.mkdir(parents=True, exist_ok=True)
                    dest = out_dir / f"{kind}.schema.json"
                else:
                    dest = out
                    dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(text, encoding="utf-8")
                _echo_wrote(f"{kind} schema", dest)
            else:
                sys.stdout.write(text)
        return

    # --- default OPORD schema mode ----------------------------------------
    schema_dict = _build_opord_schema_dict()

    if fmt is SchemaFormat.YAML:
        text = yaml.safe_dump(schema_dict, sort_keys=False, width=100)
    else:
        text = json.dumps(schema_dict, indent=2, ensure_ascii=False) + "\n"

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        _echo_wrote("OPORD schema", out)
    else:
        sys.stdout.write(text)


@app.command(help="Regenerate human-readable HTML schema docs into docs/schema/.")
def docs(
    out_dir: Path = typer.Option(
        Path("docs/schema"),
        "--out",
        "-o",
        help="Directory to write generated docs into.",
    ),
    schema_path: Path = typer.Option(
        Path("schemas/opord.schema.json"),
        "--schema",
        "-s",
        help="JSON Schema source file. Regenerated from the live model if missing.",
    ),
    force: bool = typer.Option(
        False, "--force", "-F",
        help="Regenerate tree.html even if it's newer than the JSON Schema.",
    ),
) -> None:
    try:
        from json_schema_for_humans.generate import generate_from_filename
        from json_schema_for_humans.generation_configuration import GenerationConfiguration
    except ImportError:
        typer.secho(
            "json-schema-for-humans is not installed. Install it via `uv sync --extra dev`.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    if not schema_path.exists():
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path.write_text(
            json.dumps(_build_opord_schema_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        typer.secho(f"(regenerated {schema_path})", fg=typer.colors.YELLOW)

    out_dir.mkdir(parents=True, exist_ok=True)

    from opord_builder.annex_reference import write_reference
    write_reference(out_dir / "index.html")
    typer.secho(f"Wrote {out_dir}/index.html (per-annex reference)", fg=typer.colors.GREEN)

    tree_out = out_dir / "tree.html"
    if not force and tree_out.exists() and tree_out.stat().st_mtime >= schema_path.stat().st_mtime:
        typer.secho(f"Skipped {tree_out} (up to date; pass --force to rebuild)", fg=typer.colors.YELLOW)
        return

    config = GenerationConfiguration(
        template_name="js_offline",
        expand_buttons=True,
        copy_css=True,
        copy_js=True,
        description_is_markdown=False,
        link_to_reused_ref=True,
        with_footer=False,
    )
    generate_from_filename(str(schema_path), str(tree_out), config=config)
    typer.secho(f"Wrote {tree_out} (JSON Schema tree)", fg=typer.colors.GREEN)


@app.command(help="Generate the per-annex reference page (docs/annex_reference.html).")
def reference(
    out: Path = typer.Option(
        Path("docs/annex_reference.html"),
        "--out",
        "-o",
        help="Output HTML path.",
    ),
) -> None:
    from opord_builder.annex_reference import write_reference
    _echo_wrote("annex reference", write_reference(out))


def _detect_kind(yaml_path: Path) -> str:
    """Peek at the YAML to detect document kind without full parsing."""
    import yaml as _yaml
    with open(yaml_path, "r", encoding="utf-8") as f:
        raw = _yaml.safe_load(f)
    return raw.get("kind", "opord") if isinstance(raw, dict) else "opord"


@app.command(help="Export any list-of-entries product from the OPORD as a standalone PDF/HTML/CSV.")
def export(
    input_file: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to the OPORD YAML file.",
    ),
    product: str = typer.Option(
        ...,
        "--product",
        "-p",
        help="Product alias (e.g. jpitl, pir, cap_tracks) or dotted path (e.g. 'annex.D.jpitl', 'execution.tasks_to_subordinate_units'). Run `opord list-products INPUT` to see what's available.",
    ),
    fmt: ExportFormat = typer.Option(
        ExportFormat.PDF,
        "--format",
        "-f",
        help="Output format.",
    ),
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        "-o",
        help="Output path. Defaults to output/<input-stem>_<product>.<ext>.",
    ),
) -> None:
    try:
        opord = load_opord(input_file)
    except ValidationError as exc:
        typer.secho(_fmt_validation_error(exc, input_file), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    ext = fmt.value
    slug = product.replace(".", "_").replace("/", "_")
    target = out or Path("output") / f"{input_file.stem}_{slug}.{ext}"
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        if fmt is ExportFormat.PDF:
            render_product_pdf(opord, target, product)
        elif fmt is ExportFormat.HTML:
            target.write_text(
                _inline_stylesheet(render_product_html(opord, product)),
                encoding="utf-8",
            )
        else:  # CSV
            target.write_text(render_product_csv(opord, product), encoding="utf-8")
    except ValueError as exc:
        typer.secho(f"Export failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    _echo_wrote(f"{product} {fmt.value}", target)


@app.command(help="Export kneeboard cards as 768×1024 PNG images for DCS World.")
def kneeboard(
    input_file: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to an OPORD or FRAGO YAML file containing kneeboard cards.",
    ),
    out_dir: Optional[Path] = typer.Option(
        None,
        "--out-dir",
        "-o",
        help="Output directory for PNG files. Defaults to ./output/.",
    ),
) -> None:
    kind = _detect_kind(input_file)
    try:
        if kind == "frago":
            frago, _base = load_frago(input_file)
            doc = frago
        elif kind == "warno":
            warno, _base = load_warno(input_file)
            doc = warno
        else:
            doc = load_opord(input_file)
    except ValidationError as exc:
        typer.secho(_fmt_validation_error(exc, input_file), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    if not getattr(doc, "kneeboards", []):
        typer.secho("No kneeboard cards defined in this document.", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=0)

    target_dir = out_dir or Path("output")
    paths = render_kneeboards(doc, target_dir, input_file.stem)
    for p in paths:
        _echo_wrote("kneeboard PNG", p)


def _run_delta_render(
    input_file: Path,
    out_dir: Optional[Path],
    md: bool,
    html: bool,
    pdf: bool,
    *,
    loader,
    renderer_all,
) -> None:
    try:
        obj, base = loader(input_file)
    except ValidationError as exc:
        typer.secho(_fmt_validation_error(exc, input_file), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    target_dir = out_dir or Path("output")
    stem = input_file.stem
    outputs = renderer_all(
        obj, base, target_dir, stem,
        write_markdown=md, write_html=html, write_pdf=pdf,
    )
    typer.secho(
        f"Rendered {obj.kind.upper()} {obj.sequence_number} → "
        + ", ".join(p.name for p in outputs.values()),
        fg=typer.colors.GREEN,
    )
    for kind, path in outputs.items():
        typer.echo(f"  {kind:<8}  {path}  ({path.stat().st_size:,} bytes)")


@app.command(help="Render a FRAGO (Fragmentary Order) YAML against its referenced base OPORD.")
def frago(
    input_file: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to the FRAGO YAML file (must have 'kind: frago' at top).",
    ),
    out_dir: Optional[Path] = typer.Option(
        None,
        "--out-dir",
        "-o",
        help="Output directory. Defaults to ./output/.",
    ),
    md: bool = typer.Option(True, "--md/--no-md", help="Write a Markdown file."),
    html: bool = typer.Option(True, "--html/--no-html", help="Write a standalone HTML file."),
    pdf: bool = typer.Option(True, "--pdf/--no-pdf", help="Write a PDF file."),
) -> None:
    _run_delta_render(
        input_file, out_dir, md, html, pdf,
        loader=load_frago, renderer_all=render_frago_all,
    )


@app.command(help="Render a WARNO (Warning Order) YAML. Base OPORD reference is optional.")
def warno(
    input_file: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to the WARNO YAML file (must have 'kind: warno' at top).",
    ),
    out_dir: Optional[Path] = typer.Option(
        None,
        "--out-dir",
        "-o",
        help="Output directory. Defaults to ./output/.",
    ),
    md: bool = typer.Option(True, "--md/--no-md", help="Write a Markdown file."),
    html: bool = typer.Option(True, "--html/--no-html", help="Write a standalone HTML file."),
    pdf: bool = typer.Option(True, "--pdf/--no-pdf", help="Write a PDF file."),
) -> None:
    _run_delta_render(
        input_file, out_dir, md, html, pdf,
        loader=load_warno, renderer_all=render_warno_all,
    )


@app.command("list-products", help="List every exportable list-of-entries product in an OPORD (short alias + dotted path + entry count).")
def list_products(
    input_file: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to the OPORD YAML file.",
    ),
) -> None:
    try:
        opord = load_opord(input_file)
    except ValidationError as exc:
        typer.secho(_fmt_validation_error(exc, input_file), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    products = discover_products(opord)
    if not products:
        typer.secho("No list-of-entries products found in this OPORD.", fg=typer.colors.YELLOW)
        return

    # Build reverse alias map for each discovered path.
    alias_by_path = {path: name for name, (path, _, _) in _PRODUCT_ALIASES.items()}
    typer.secho(f"Products exportable from {input_file.name}:", fg=typer.colors.CYAN)
    typer.echo(f"  {'alias':<20} {'path':<58} {'entries':>7}  type")
    typer.echo(f"  {'-'*20} {'-'*58} {'-'*7}  {'-'*20}")
    for path, count, model_name in sorted(products):
        alias = alias_by_path.get(path, "")
        typer.echo(f"  {alias:<20} {path:<58} {count:>7}  {model_name}")
    typer.echo()
    typer.secho(
        "Export with:  opord export INPUT -p <alias-or-path> -f pdf|html|csv",
        fg=typer.colors.CYAN,
    )


@app.command(help="Scaffold a starter OPORD tree (main.yaml + annexes/annex_*.yaml).")
def init(
    target_dir: Path = typer.Argument(
        ...,
        file_okay=False,
        dir_okay=True,
        help="Directory to create. Will be created if missing.",
    ),
    force: bool = typer.Option(
        False, "--force", "-F",
        help="Overwrite existing files in target_dir (default: refuse if any collide).",
    ),
    with_data_sources: bool = typer.Option(
        False,
        "--with-data-sources",
        help="Scaffold a data_sources/ directory with targeting stubs.",
    ),
) -> None:
    from opord_builder import scaffolds

    target_dir.mkdir(parents=True, exist_ok=True)
    annex_dir = target_dir / "annexes"
    annex_dir.mkdir(exist_ok=True)

    letters = scaffolds.published_letters()
    planned: list[Path] = [target_dir / "main.yaml"] + [
        annex_dir / f"annex_{ltr.lower()}.yaml" for ltr in letters
    ]

    if with_data_sources:
        ds_dir = target_dir / "data_sources" / "fires"
        planned += [
            ds_dir / "jpitl.yaml",
            ds_dir / "tst.yaml",
            ds_dir / "hpt.yaml",
        ]

    existing = [p for p in planned if p.exists()]
    if existing and not force:
        typer.secho(
            "Refusing to overwrite existing files (pass --force to override):",
            fg=typer.colors.RED, err=True,
        )
        for p in existing:
            typer.secho(f"  {p}", err=True)
        raise typer.Exit(code=1)

    # --- data-source block for main.yaml (when requested) -----------------
    data_source_block = ""
    if with_data_sources:
        data_source_block = (
            "data_sources:\n"
            "  - source: data_sources/fires/jpitl.yaml\n"
            "    target: annexes.D.typed_body.jpitl\n"
            "  - source: data_sources/fires/tst.yaml\n"
            "    target: annexes.D.typed_body.time_sensitive_targets\n"
            "  - source: data_sources/fires/hpt.yaml\n"
            "    target: annexes.D.typed_body.high_payoff_target_list"
        )

    annex_includes = [f"annexes/annex_{ltr.lower()}.yaml" for ltr in letters]
    (target_dir / "main.yaml").write_text(
        scaffolds.main_yaml(
            schema_rel_path="schemas/opord.schema.json",
            annex_files=annex_includes,
            data_source_block=data_source_block,
        ),
        encoding="utf-8",
    )
    _echo_wrote("main.yaml", target_dir / "main.yaml")
    for ltr in letters:
        path = annex_dir / f"annex_{ltr.lower()}.yaml"
        path.write_text(scaffolds.annex_yaml(ltr), encoding="utf-8")
    typer.secho(
        f"  + {len(letters)} annex stubs under {annex_dir}/",
        fg=typer.colors.GREEN,
    )

    if with_data_sources:
        ds_dir = target_dir / "data_sources" / "fires"
        ds_dir.mkdir(parents=True, exist_ok=True)
        (ds_dir / "jpitl.yaml").write_text(scaffolds.jpitl_yaml(), encoding="utf-8")
        (ds_dir / "tst.yaml").write_text(scaffolds.tst_yaml(), encoding="utf-8")
        (ds_dir / "hpt.yaml").write_text(scaffolds.hpt_yaml(), encoding="utf-8")
        typer.secho(
            f"  + 3 data-source stubs under {ds_dir}/",
            fg=typer.colors.GREEN,
        )

    typer.secho(
        f"\nNext: edit {target_dir}/main.yaml and run "
        f"`opord render {target_dir}/main.yaml`.",
    )


@app.command(help="Watch a YAML OPORD and re-render on file change.")
def watch(
    input_file: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to the OPORD YAML file to watch.",
    ),
    out_dir: Optional[Path] = typer.Option(
        None, "--out-dir", "-o",
        help="Output directory. Defaults to ./output/.",
    ),
    md: bool = typer.Option(True, "--md/--no-md", help="Write a Markdown file."),
    html: bool = typer.Option(True, "--html/--no-html", help="Write a standalone HTML file."),
    pdf: bool = typer.Option(True, "--pdf/--no-pdf", help="Write a PDF file."),
) -> None:
    from watchfiles import watch as _watch

    target_dir = out_dir or input_file.parent
    stem = input_file.stem
    watch_root = input_file.parent.resolve()

    def _render_once() -> None:
        try:
            opord = load_opord(input_file)
        except ValidationError as exc:
            typer.secho(_fmt_validation_error(exc, input_file), fg=typer.colors.RED, err=True)
            return
        except Exception as exc:
            typer.secho(f"Render failed: {exc}", fg=typer.colors.RED, err=True)
            return
        outputs = render_all(
            opord, target_dir, stem, write_markdown=md, write_html=html, write_pdf=pdf
        )
        typer.secho(
            f"Rendered {input_file.name} → "
            + ", ".join(p.name for p in outputs.values()),
            fg=typer.colors.GREEN,
        )

    # Initial render so the user sees current state.
    _render_once()
    typer.secho(f"Watching {watch_root} for YAML changes (Ctrl-C to stop)...",
                fg=typer.colors.CYAN)

    # watchfiles filters by path; we care only about *.yaml under watch_root.
    def _is_yaml(_change, path: str) -> bool:
        return path.endswith((".yaml", ".yml"))

    try:
        for _ in _watch(watch_root, watch_filter=_is_yaml):
            _render_once()
    except KeyboardInterrupt:  # pragma: no cover
        typer.secho("\nStopped.", fg=typer.colors.CYAN)


if __name__ == "__main__":  # pragma: no cover
    app()
