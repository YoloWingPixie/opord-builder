# ruff: noqa: B008
"""`opord` CLI entry point."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

import click
import typer
import yaml

from opord_builder.docs import KINDS
from opord_builder.load import DocumentError, read, validate_document

app = typer.Typer(
    name="opord",
    help="Render OpenAIX orders (OPORD, FRAGO, WARNO), SPINS and kneeboards.",
    no_args_is_help=True,
    add_completion=False,
)
INPUT = typer.Argument(..., exists=True, dir_okay=False, readable=True)
OUT_DIR = typer.Option(
    None, "--out-dir", "-o", help="Output directory. Defaults to ./output/."
)
MD = typer.Option(True, "--md/--no-md", help="Write a Markdown file.")
HTML = typer.Option(True, "--html/--no-html", help="Write a standalone HTML file.")
PDF = typer.Option(True, "--pdf/--no-pdf", help="Write a PDF file.")
THEME = typer.Option(
    None,
    "--theme",
    help="Document theme, e.g. wp90 (see templates/themes/). Overrides the document's `theme`.",
)


class ExportFormat(str, Enum):
    PDF = "pdf"
    HTML = "html"
    CSV = "csv"


def fail(message: str, code: int = 2) -> typer.Exit:
    typer.secho(message, fg=typer.colors.RED, err=True)
    return typer.Exit(code=code)


def wrote(label: str, path: Path) -> None:
    typer.secho(
        f"Wrote {label} → {path}  ({path.stat().st_size:,} bytes)",
        fg=typer.colors.GREEN,
    )


def load(path: Path, base: Path | None = None, kind: str | None = None):
    from opord_builder.order import load_order

    try:
        order = load_order(path, base)
    except (DocumentError, ValueError, OSError, yaml.YAMLError) as exc:
        raise fail(str(exc)) from exc
    if kind and order.kind != kind:
        raise fail(f"{path}: this is a {order.kind.upper()}, not a {kind.upper()}")
    return order


def render_order(
    path: Path,
    out_dir: Path | None,
    md: bool,
    html: bool,
    pdf: bool,
    base: Path | None,
    kind: str | None,
    theme: str | None = None,
):
    from opord_builder import themes
    from opord_builder.render import render_all

    order = load(path, base, kind)
    try:
        theme = themes.resolve(theme, order.theme)
    except ValueError as exc:
        raise fail(str(exc)) from exc
    outputs = render_all(
        order, out_dir or Path("output"), path.stem, md, html, pdf, theme
    )
    typer.secho(
        f"Rendered {path.name}  →  " + ", ".join(p.name for p in outputs.values()),
        fg=typer.colors.GREEN,
    )
    for label, out in outputs.items():
        typer.echo(f"  {label:<8}  {out}  ({out.stat().st_size:,} bytes)")


@app.command(help="Render an OPORD (or any order) to Markdown, HTML and PDF.")
def render(
    input_file: Path = INPUT,
    out_dir: Path | None = OUT_DIR,
    md: bool = MD,
    html: bool = HTML,
    pdf: bool = PDF,
    theme: str | None = THEME,
) -> None:
    render_order(input_file, out_dir, md, html, pdf, None, None, theme)


@app.command(help="Render a FRAGO against its base order.")
def frago(
    input_file: Path = INPUT,
    base: Path | None = typer.Option(
        None,
        "--base",
        exists=True,
        dir_okay=False,
        help="The base order (default: the FRAGO's base_order_path).",
    ),
    out_dir: Path | None = OUT_DIR,
    md: bool = MD,
    html: bool = HTML,
    pdf: bool = PDF,
    theme: str | None = THEME,
) -> None:
    render_order(input_file, out_dir, md, html, pdf, base, "frago", theme)


@app.command(
    help="Render a WARNO (an opord marked document_kind: warno). The base order is optional."
)
def warno(
    input_file: Path = INPUT,
    out_dir: Path | None = OUT_DIR,
    md: bool = MD,
    html: bool = HTML,
    pdf: bool = PDF,
    theme: str | None = THEME,
) -> None:
    render_order(input_file, out_dir, md, html, pdf, None, "warno", theme)


@app.command(help="Render a numbered SPINS publication and its standing baseline.")
def spins(
    input_file: Path = INPUT,
    out_dir: Path | None = OUT_DIR,
    md: bool = MD,
    html: bool = HTML,
    pdf: bool = PDF,
    theme: str | None = THEME,
) -> None:
    from opord_builder.spins import load_spins, render_spins_all

    try:
        outputs = render_spins_all(
            load_spins(input_file),
            out_dir or Path("output"),
            input_file.stem,
            write_markdown=md,
            write_html=html,
            write_pdf=pdf,
            theme=theme,
        )
    except (DocumentError, ValueError, OSError, yaml.YAMLError) as exc:
        raise fail(f"{input_file}: {exc}") from exc
    for label, out in outputs.items():
        wrote(f"SPINS {label}", out)


@app.command(
    help="Export a list from the order (an alias such as jpitl, or a JSON Pointer) as PDF, HTML or CSV."
)
def export(
    input_file: Path = INPUT,
    product: str = typer.Option(
        ...,
        "--product",
        "-p",
        help="Alias (jpitl, pir, cap_tracks, ...) or a JSON Pointer into the document. `opord list-products` shows what exists.",
    ),
    fmt: ExportFormat = typer.Option(
        ExportFormat.PDF, "--format", "-f", help="Output format."
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        "-o",
        help="Output path. Defaults to output/<input-stem>_<product>.<ext>.",
    ),
    theme: str | None = THEME,
) -> None:
    from opord_builder import render as r
    from opord_builder import themes

    order = load(input_file)
    try:
        theme = themes.resolve(theme, order.theme)
    except ValueError as exc:
        raise fail(str(exc)) from exc
    target = (
        out
        or Path("output")
        / f"{input_file.stem}_{product.strip('/').replace('/', '_')}.{fmt.value}"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if not r.product_rows(order, product)[2]:
        raise fail(f"Export failed: {product!r} has no entries in this order")
    if fmt is ExportFormat.PDF:
        r.write_pdf(r.render_product_html(order, product, theme), target, theme)
    elif fmt is ExportFormat.HTML:
        target.write_text(
            r.render_product_html(order, product, theme), encoding="utf-8"
        )
    else:
        target.write_text(r.render_product_csv(order, product), encoding="utf-8")
    wrote(f"{product} {fmt.value}", target)


@app.command(
    "list-products",
    help="List the exportable lists of an order: alias, pointer and entry count.",
)
def list_products(input_file: Path = INPUT) -> None:
    from opord_builder.render import discover_products

    found = discover_products(load(input_file))
    if not found:
        typer.secho("No lists found in this order.", fg=typer.colors.YELLOW)
        return
    typer.echo(f"  {'alias':<20} {'pointer':<80} entries")
    for alias, pointer, count in found:
        typer.echo(f"  {alias:<20} {pointer:<80} {count:>7}")
    typer.secho(
        "Export with:  opord export INPUT -p <alias-or-pointer> -f pdf|html|csv",
        fg=typer.colors.CYAN,
    )


@app.command(
    help="Export kneeboard cards as 768x1024 PNGs, from an order, an ATO, or both."
)
def kneeboard(
    input_file: Path | None = typer.Argument(
        None,
        exists=True,
        dir_okay=False,
        readable=True,
        help="An order with kneeboard cards.",
    ),
    out_dir: Path | None = OUT_DIR,
    ato: Path | None = typer.Option(
        None,
        "--ato",
        exists=True,
        dir_okay=False,
        help="OpenAIX ATO: one card per flight.",
    ),
    flight: str | None = typer.Option(
        None, "--flight", help="Only this ATO flight id (needs --ato)."
    ),
    resources: Path | None = typer.Option(
        None,
        "--resources",
        exists=True,
        dir_okay=False,
        help="OpenAIX resources document for the ATO (needs --ato).",
    ),
    opord: Path | None = typer.Option(
        None,
        "--opord",
        exists=True,
        dir_okay=False,
        help="OpenAIX opord for the altimeter setting (needs --ato).",
    ),
    standard: Path | None = typer.Option(
        None,
        "--standard",
        exists=True,
        dir_okay=False,
        help="OpenAIX comms standard that fills blank comm cells (needs --ato).",
    ),
) -> None:
    from opord_builder import kneeboard as kb

    if ato is None and (flight or resources or opord or standard):
        raise fail("--flight, --resources, --opord and --standard need --ato.")
    if ato is None and input_file is None:
        raise fail("Give an INPUT_FILE, --ato, or both.")
    try:
        if ato is None:
            cards, warns = kb.cards_from_document(input_file), []
        else:
            cards, warns = kb.cards_from_files(ato, resources, flight, opord, standard)
            if (
                input_file is not None
            ):  # the cards authored in INPUT_FILE override the ATO's
                cards, extra = kb.merge(
                    cards,
                    kb.cards_from_document(input_file),
                    keep_unmatched=flight is None,
                )
                warns += extra
    except (DocumentError, ValueError, OSError, yaml.YAMLError) as exc:
        raise fail(str(exc)) from exc
    for w in warns:
        typer.secho(f"warning: {w}", fg=typer.colors.YELLOW, err=True)
    if not cards:
        typer.secho("No kneeboard cards defined.", fg=typer.colors.YELLOW, err=True)
        return
    for path in kb.render_cards(
        cards, out_dir or Path("output"), (input_file or ato).stem
    ):
        wrote("kneeboard PNG", path)


@app.command(help="Scaffold a starter OPORD (opord.yaml plus one stub per annex).")
def init(
    target_dir: Path = typer.Argument(
        ..., file_okay=False, dir_okay=True, help="Directory to create."
    ),
    force: bool = typer.Option(
        False, "--force", "-F", help="Overwrite existing files."
    ),
) -> None:
    from opord_builder import scaffolds

    files = scaffolds.files()
    clash = [target_dir / name for name in files if (target_dir / name).exists()]
    if clash and not force:
        raise fail(
            "Refusing to overwrite (pass --force):\n"
            + "\n".join(f"  {p}" for p in clash),
            1,
        )
    for name, text in files.items():
        (target_dir / name).parent.mkdir(parents=True, exist_ok=True)
        (target_dir / name).write_text(text, encoding="utf-8")
    typer.secho(f"Wrote {len(files)} files under {target_dir}/", fg=typer.colors.GREEN)
    typer.echo(
        f"Next: edit {target_dir}/opord.yaml and run `opord render {target_dir}/opord.yaml`."
    )


@app.command(help="Watch an order and re-render it when a YAML file changes.")
def watch(
    input_file: Path = INPUT,
    out_dir: Path | None = OUT_DIR,
    md: bool = MD,
    html: bool = HTML,
    pdf: bool = PDF,
    theme: str | None = THEME,
) -> None:
    from watchfiles import watch as watch_files

    def once() -> None:
        try:
            render_order(
                input_file,
                out_dir or input_file.parent,
                md,
                html,
                pdf,
                None,
                None,
                theme,
            )
        except typer.Exit:
            pass

    once()
    root = input_file.parent.resolve()
    typer.secho(
        f"Watching {root} for YAML changes (Ctrl-C to stop)...", fg=typer.colors.CYAN
    )
    try:
        for _ in watch_files(
            root, watch_filter=lambda _c, p: p.endswith((".yaml", ".yml", ".json"))
        ):
            once()
    except KeyboardInterrupt:  # pragma: no cover
        typer.secho("\nStopped.", fg=typer.colors.CYAN)


@app.command(
    name="validate-openaix",
    help="Validate OpenAIX documents (YAML or JSON), extensions included.",
)
def validate_openaix(
    files: list[Path] = typer.Argument(..., exists=True, dir_okay=False, readable=True),
) -> None:
    failed = False
    for path in files:
        try:
            errors = validate_document(read(path))
        except (OSError, ValueError, yaml.YAMLError) as exc:
            typer.secho(f"{path}: cannot read: {exc}", fg=typer.colors.RED, err=True)
            failed = True
            continue
        for err in errors:
            typer.secho(
                f"{path}: {err.pointer or '/'}: {err.message}",
                fg=typer.colors.RED,
                err=True,
            )
        failed = failed or bool(errors)
        if not errors:
            typer.echo(f"{path}: ok")
    if failed:
        raise typer.Exit(code=1)


@app.command(
    help="Write the generated schema files (complete-schema page, annex reference, bundled schemas)."
)
def docs(
    check: bool = typer.Option(
        False, "--check", help="Write nothing; exit 1 when a generated file is stale."
    ),
    out_dir: Path = typer.Option(
        None,
        "--out-dir",
        help="Repository root to write to. Defaults to this checkout.",
    ),
) -> None:
    from opord_builder import docs as d

    root = out_dir or d.ROOT
    files = d.generated()
    stale = [
        p
        for p, text in files.items()
        if not (root / p).is_file() or (root / p).read_text(encoding="utf-8") != text
    ]
    if check:
        if stale:
            raise fail(
                "Stale or missing generated files (run `opord docs`):\n"
                + "\n".join(f"  {p}" for p in stale),
                1,
            )
        typer.echo(f"{len(files)} generated files are current.")
        return
    for p, text in files.items():
        (root / p).parent.mkdir(parents=True, exist_ok=True)
        (root / p).write_text(text, encoding="utf-8")
        wrote("docs", root / p)


@app.command(help="Write the per-annex reference page (docs/annex_reference.html).")
def reference(
    out: Path = typer.Option(
        Path("docs/annex_reference.html"), "--out", help="Output file."
    ),
) -> None:
    from opord_builder.docs import reference_html

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(reference_html(), encoding="utf-8")
    wrote("annex reference", out)


@app.command(
    help="Print the single-file JSON Schema for a document type, extensions included."
)
def schema(
    document_type: str = typer.Option(
        "opord",
        "--document-type",
        "-t",
        click_type=click.Choice(KINDS),
        help="opord, frago, spins, ato or resources.",
    ),
    out: Path | None = typer.Option(
        None, "--out", help="Write here instead of stdout."
    ),
) -> None:
    from opord_builder.docs import bundled

    text = json.dumps(bundled(document_type), indent=2, ensure_ascii=False) + "\n"
    if out is None:
        typer.echo(text, nl=False)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    wrote(f"{document_type} schema", out)


if __name__ == "__main__":  # pragma: no cover
    app()
