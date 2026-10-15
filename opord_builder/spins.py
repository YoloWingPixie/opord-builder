"""Load, compose, and render numbered SPINS publications."""

from __future__ import annotations

import base64
import json
from copy import deepcopy
from enum import Enum
from html import escape
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from opord_builder._paths import SPINS_DEFAULT_LAYOUT, TEMPLATES_DIR
from opord_builder.renderer import _load_yaml_with_variables, _render_document_all
from opord_builder.schema.data_sources import DATA_SOURCE_REGISTRY
from opord_builder.schema.spins import (
    SPINS,
    CrossReference,
    FigureBlock,
    ListBlock,
    OpenAIXTableBlock,
    Paragraph,
    Section,
    SourceTableBlock,
    TableBlock,
    TextRun,
    iter_blocks,
    iter_values,
)
from opord_builder.spins_numbering import number_publication
from opord_builder.spins_openaix import OpenAIXSources, openaix_table

IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}
HTML_MARKS = {"bold": "strong", "italic": "em", "underline": "u", "code": "code"}
MARKDOWN_MARKS = {
    "bold": ("**", "**"),
    "italic": ("*", "*"),
    "underline": ("<u>", "</u>"),
    "code": ("<code>", "</code>"),
}
LIST_TYPES = {
    "bullet": None,
    "decimal": "1",
    "lower_alpha": "a",
    "upper_alpha": "A",
    "lower_roman": "i",
    "upper_roman": "I",
}


def _locations(blocks, path=()):
    for index, block in enumerate(blocks):
        here = (*path, index)
        if block.id:
            yield block.id, (blocks, index, here)
        if isinstance(block, (Section, Paragraph)):
            yield from _locations(block.blocks, here)
        elif isinstance(block, ListBlock):
            for item_index, item in enumerate(block.items):
                yield from _locations(item.blocks, (*here, "item", item_index))


def _check_changes(baseline, changes):
    locations = dict(_locations(baseline.content))
    writes = []
    additions = []
    introduced_ids = set()
    for change in changes:
        if change.op in ("add", "replace"):
            ids = [block.id for _, block in iter_blocks([change.block]) if block.id]
            owned_ids = set()
            if change.op == "replace" and change.target in locations:
                target_path = locations[change.target][2]
                owned_ids = {
                    name
                    for name, (_, _, path) in locations.items()
                    if path[: len(target_path)] == target_path
                }
            conflicts = set(ids) & ((set(locations) - owned_ids) | introduced_ids)
            if len(ids) != len(set(ids)) or conflicts:
                raise ValueError(
                    "amendment block identifiers conflict with existing blocks"
                )
            introduced_ids.update(ids)
        if change.op == "add":
            anchor = change.after or change.before
            if anchor and anchor not in locations:
                raise ValueError(
                    f"insertion anchor {anchor!r} is not a sibling in the baseline"
                )
            if change.parent:
                if change.parent not in locations:
                    raise ValueError(f"unknown amendment parent {change.parent!r}")
                container, index, path = locations[change.parent]
                if not isinstance(container[index], (Section, Paragraph)):
                    raise ValueError("amendment parent must be a section or paragraph")
            else:
                path = ()
            additions.append((path, change.after or change.before))
            continue
        if change.target not in locations:
            raise ValueError(f"unknown amendment target {change.target!r}")
        path = locations[change.target][2]
        if any(
            path[: len(other)] == other or other[: len(path)] == path
            for other in writes
        ):
            raise ValueError("amendments cannot replace/remove overlapping blocks")
        writes.append(path)
        if change.op == "replace" and change.block.id != change.target:
            raise ValueError("replacement must retain its target identifier")
    removed = {change.target for change in changes if change.op == "remove"}
    for path, after in additions:
        if any(path[: len(write)] == write for write in writes):
            raise ValueError("cannot add inside a replaced or removed block")
        if after in removed:
            raise ValueError("cannot insert relative to a removed block")


def _apply_changes(baseline: SPINS, amendment: SPINS):
    content = deepcopy(baseline.content)
    last_insertions = {}
    for change in amendment.changes:
        locations = dict(_locations(content))
        if change.op == "add":
            if change.parent:
                parent_list, parent_index, _ = locations[change.parent]
                destination = parent_list[parent_index].blocks
            else:
                destination = content
            position = len(destination)
            if change.after or change.before:
                siblings = {
                    block.id: i for i, block in enumerate(destination) if block.id
                }
                sibling = change.after or change.before
                if sibling not in siblings:
                    raise ValueError(f"insertion anchor {sibling!r} is not a sibling")
                position = siblings[sibling] + (1 if change.after else 0)
            key = (change.parent, change.after)
            if change.after and key in last_insertions:
                position = (
                    next(
                        i
                        for i, block in enumerate(destination)
                        if block is last_insertions[key]
                    )
                    + 1
                )
            inserted = deepcopy(change.block)
            destination.insert(position, inserted)
            if change.after:
                last_insertions[key] = inserted
        else:
            container, index, _ = locations[change.target]
            if change.op == "remove":
                del container[index]
            else:
                container[index] = deepcopy(change.block)
    return content


def compose_spins(baseline: SPINS, amendment: SPINS) -> SPINS:
    """Apply one mission amendment to a standing baseline without mutating either input."""
    if baseline.scope != "standing" or baseline.base or baseline.changes:
        raise ValueError("baseline must be complete standing SPINS")
    if not amendment.base or (baseline.meta.id, baseline.meta.revision) != (
        amendment.base.id,
        amendment.base.revision,
    ):
        raise ValueError(
            "baseline identifier/revision does not match the pinned reference"
        )
    if (
        baseline.period
        and amendment.period
        and (
            amendment.period.start < baseline.period.start
            or amendment.period.end > baseline.period.end
        )
    ):
        raise ValueError("mission period exceeds baseline validity")
    _check_changes(baseline, amendment.changes)
    result = amendment.model_copy(deep=True)
    result.content = _apply_changes(baseline, amendment)
    result.content.extend(deepcopy(amendment.content))
    citations = {reference.id: reference for reference in baseline.meta.references}
    for reference in result.meta.references:
        if reference.id in citations and citations[reference.id] != reference:
            raise ValueError(f"conflicting publication reference {reference.id!r}")
        citations[reference.id] = reference
    result.meta.references = list(citations.values())
    if result.meta.classification is None:
        result.meta.classification = baseline.meta.classification
    if result.meta.handling is None:
        result.meta.handling = baseline.meta.handling
    result.presentation = baseline.presentation.model_copy(
        update=amendment.presentation.model_dump(exclude_unset=True)
    )
    result.base = None
    result.changes = []
    return SPINS.model_validate(result.model_dump())


def _source_table(
    block: SourceTableBlock, directory: Path, variables: dict
) -> TableBlock:
    path = directory / block.source
    data, _ = _load_yaml_with_variables(path, extra_vars=variables)
    model = (
        DATA_SOURCE_REGISTRY.get(data.get("kind")) if isinstance(data, dict) else None
    )
    if model is None:
        raise ValueError(f"{path}: unknown standalone data-source kind")
    source = model.model_validate(data)
    if not source.entries:
        raise ValueError(f"{path}: source table has no entries")
    rows = []
    for entry in source.entries:
        row = {}
        for column in block.columns:
            if column.field not in type(entry).model_fields:
                raise ValueError(f"{path}: unknown field {column.field!r}")
            value = getattr(entry, column.field)
            if isinstance(value, Enum):
                value = value.value
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise ValueError(
                    f"{path}: field {column.field!r} must be scalar for a source table"
                )
            row[column.key] = "" if value is None else str(value)
        rows.append(row)
    return TableBlock(
        kind="table",
        id=block.id,
        caption=block.caption,
        columns=[column.model_dump(exclude={"field"}) for column in block.columns],
        rows=rows,
    )


def _prepare_blocks(blocks, directory, variables, openaix=None):
    prepared = []
    openaix = openaix or OpenAIXSources(None, directory)
    for original in blocks:
        block = original.model_copy(deep=True)
        if isinstance(block, SourceTableBlock):
            block = _source_table(block, directory, variables)
        elif isinstance(block, OpenAIXTableBlock):
            block = openaix_table(block, openaix)
            if block is None:
                continue
        elif isinstance(block, FigureBlock):
            block.src = str((directory / block.src).resolve())
        elif isinstance(block, Section):
            block.blocks = _prepare_blocks(block.blocks, directory, variables, openaix)
            if not block.blocks:
                continue  # every child was skipped: leave no empty heading
        elif isinstance(block, Paragraph):
            block.blocks = _prepare_blocks(block.blocks, directory, variables, openaix)
        elif isinstance(block, ListBlock):
            for item in block.items:
                item.blocks = _prepare_blocks(
                    item.blocks, directory, variables, openaix
                )
        prepared.append(block)
    return prepared


def _check_cross_references(document: SPINS) -> None:
    ids = {block.id for _, block in iter_blocks(document.content) if block.id}
    for value in iter_values(document.content):
        if isinstance(value, CrossReference) and value.target not in ids:
            raise ValueError(
                f"cross-reference to {value.target!r}, a block removed because its OpenAIX data is absent"
            )


def _build_spins(data, variables, directory: Path) -> SPINS:
    document = SPINS.model_validate(data)
    openaix = OpenAIXSources(document.openaix, directory)
    document.content = _prepare_blocks(document.content, directory, variables, openaix)
    for change in document.changes:
        if change.op in ("add", "replace"):
            prepared = _prepare_blocks([change.block], directory, variables, openaix)
            if not prepared:
                raise ValueError(
                    f"amendment {change.op} block {change.block.id!r} has no OpenAIX data to show"
                )
            change.block = prepared[0]
    if document.base is None:
        _check_cross_references(document)
    return document


def _read_spins(path: Path) -> SPINS:
    data, variables = _load_yaml_with_variables(path)
    return _build_spins(data, variables, path.parent)


def load_spins(path: Path | str) -> SPINS:
    """Load local YAML/includes, typed source tables, and one pinned standing baseline."""
    path = Path(path).resolve()
    document = _read_spins(path)
    if document.base:
        baseline_path = (path.parent / document.base.path).resolve()
        if baseline_path == path:
            raise ValueError("SPINS cannot reference itself as its baseline")
        baseline = _read_spins(baseline_path)
        document = compose_spins(baseline, document)
    return document


def load_default_spins(
    *,
    spins: Path | str | None = None,
    resources: Path | str | None = None,
    ato: Path | str | None = None,
    aco: Path | str | None = None,
    airfields: list[Path | str] | tuple[Path | str, ...] = (),
) -> SPINS:
    """Render-ready SPINS from the shipped default layout and the given OpenAIX files.

    Publication metadata and period come from the OpenAIX SPINS document when it has them.
    Sections whose data is absent are left out."""
    data, variables = _load_yaml_with_variables(SPINS_DEFAULT_LAYOUT)
    refs = {"spins": spins, "resources": resources, "ato": ato, "aco": aco}
    data["openaix"] = {
        **{k: str(Path(v).resolve()) for k, v in refs.items() if v},
        **({"airfields": [str(Path(p).resolve()) for p in airfields]} if airfields else {}),
    }
    if spins:
        source = json.loads(Path(spins).read_text(encoding="utf-8"))
        meta = source.get("meta", {})
        for key in ("id", "title", "revision", "operation", "issuing_unit", "author", "issued_at"):
            if meta.get(key):
                data["meta"][key] = meta[key]
        if source.get("scope") == "mission" and source.get("period"):
            data["scope"] = "mission"
        if source.get("period"):
            data["period"] = source["period"]
    return _build_spins(data, variables, SPINS_DEFAULT_LAYOUT.parent)


def _image_uri(block: FigureBlock) -> str:
    path = Path(block.src)
    mime = IMAGE_TYPES.get(path.suffix.lower())
    if mime is None:
        raise ValueError(f"unsupported figure format: {path}")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _markdown_escape(text):
    for character in ("\\", "*", "_", "[", "]", "<", ">", "|", "`", "#"):
        text = text.replace(character, "\\" + character)
    return text


def _rich_renderer(document, numbering, *, html):
    references = {reference.id: reference for reference in document.meta.references}
    transform = str.upper if document.presentation.text_case == "uppercase" else str

    def render(value):
        if value is None:
            return ""
        if isinstance(value, str):
            text = transform(value)
            return Markup(escape(text)) if html else _markdown_escape(text)
        output = []
        for run in value:
            if isinstance(run, TextRun):
                text = transform(run.text)
                text = escape(text) if html else _markdown_escape(text)
                for mark in run.marks:
                    if html:
                        tag = HTML_MARKS[mark]
                        text = f"<{tag}>{text}</{tag}>"
                    else:
                        before, after = MARKDOWN_MARKS[mark]
                        text = before + text + after
                output.append(text)
                continue
            if isinstance(run, CrossReference):
                label = run.text or numbering.references[run.target]
                href = f"#node-{run.target}"
            else:
                reference = references[run.citation]
                label = run.text or numbering.citations[reference.id]
                href = f"#citation-{reference.id}"
            label = transform(label)
            output.append(
                f'<a href="{href}">{escape(label)}</a>'
                if html
                else f"[{_markdown_escape(label)}]({href})"
            )
        text = "".join(output)
        return Markup(text) if html else text

    return render


def _context(document):
    if document.base or document.changes:
        raise ValueError("load and compose SPINS before rendering")
    document = document.model_copy(deep=True)
    document.content = _prepare_blocks(
        document.content,
        Path.cwd(),
        {},
        OpenAIXSources(document.openaix, Path.cwd()),
    )
    numbering = number_publication(document)
    figures = {
        path: _image_uri(block)
        for path, block in iter_blocks(document.content)
        if isinstance(block, FigureBlock)
    }
    contents = [
        (path, block)
        for path, block in iter_blocks(document.content)
        if isinstance(block, Section)
    ]
    return {
        "document": document,
        "numbering": numbering,
        "labels": numbering.labels,
        "citation_labels": numbering.citations,
        "figures": figures,
        "contents": contents,
        "citations": {
            reference.id: reference for reference in document.meta.references
        },
        "anchor": lambda block, path: (
            "node-" + block.id if block.id else "position-" + path
        ),
        "list_types": LIST_TYPES,
    }


def _render(document, *, html):
    context = _context(document)
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(enabled_extensions=("j2",)) if html else False,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["rich"] = _rich_renderer(
        context["document"], context["numbering"], html=html
    )
    env.globals["rich_html"] = _rich_renderer(
        context["document"], context["numbering"], html=True
    )
    context["stylesheet"] = (TEMPLATES_DIR / "spins.css").read_text(encoding="utf-8")
    template = "spins.html.j2" if html else "spins.md.j2"
    return env.get_template(template).render(**context)


def render_spins_html(document: SPINS) -> str:
    """Render a standalone publication with embedded styles and local figures."""
    return _render(document, html=True)


def render_spins_markdown(document: SPINS) -> str:
    return _render(document, html=False)


def render_spins_pdf(
    document: SPINS, path: Path | str, *, html: str | None = None
) -> Path:
    from weasyprint import HTML

    path = Path(path)
    HTML(string=html if html is not None else render_spins_html(document)).write_pdf(
        path
    )
    return path


def render_spins_all(
    document: SPINS,
    out_dir: Path | str,
    stem: str,
    *,
    write_markdown=True,
    write_html=True,
    write_pdf=True,
):
    return _render_document_all(
        out_dir,
        stem,
        render_md_fn=lambda: render_spins_markdown(document),
        render_html_fn=lambda: render_spins_html(document),
        render_pdf_fn=lambda path, html: render_spins_pdf(document, path, html=html),
        prepare_html_fn=lambda html: html,
        write_markdown=write_markdown,
        write_html=write_html,
        write_pdf=write_pdf,
    )
