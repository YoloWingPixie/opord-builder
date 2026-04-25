"""Walks the Pydantic schema and emits a per-annex + full-OPORD reference page."""

from __future__ import annotations

import re
import types
import typing
from html import escape
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from opord_builder._paths import EXAMPLE_FULL_YAML
from opord_builder.appendix_catalog import APPENDIX_CATALOG
from opord_builder.schema import CANONICAL_ANNEXES, RESERVED_LETTERS
from opord_builder.schema._base import literal_value
from opord_builder.schema.annexes import AnnexTypedBody
from opord_builder.schema.core import (
    OPORD,
    Annex,
    Appendix,
    AreaOfOperations,
    AttachmentsDetachments,
    Authentication,
    CallSignEntry,
    CallSignGroup,
    CCIR,
    CivilConsiderations,
    Command,
    CommandAndSignal,
    CommandersIntent,
    ConceptOfOperations,
    Control,
    CoordinatingInstructions,
    EnemyForces,
    Execution,
    FrequencyChannel,
    FrequencyTable,
    FriendlyForces,
    Header,
    HealthServices,
    HigherHeadquarters,
    Logistics,
    PersonnelServices,
    Reference,
    Signal,
    Situation,
    SubordinateTask,
    Sustainment,
    Terrain,
    Unit,
    Weather,
)

# Compiled regexes used by YAML slicers — module-level to avoid per-call recompile.
_TOP_KEY_RE = re.compile(r"^([a-z_]+):(?:\s.*)?$", re.MULTILINE)
_ANNEX_ENTRY_RE = re.compile(r"(^  - letter: ([A-Z])$)", re.MULTILINE)
_OUTDENT_RE = re.compile(r"\n(?=[A-Za-z_])")


def _load_example_full() -> tuple[dict[str, str], dict[str, str], str]:
    """Return (top_level_slices, annex_slices, raw_text) parsed from example_full.yaml in one pass.

    top_level: {key -> yaml snippet} for every column-0 key (header, situation,
    mission, execution, sustainment, command_and_signal, annexes, authentication).
    annex: {letter -> yaml snippet} for every `- letter: X` entry inside the
    annexes block. raw_text is the full file contents (empty string if missing)
    so callers needing a preview slice do not re-read the file.
    """
    try:
        text = EXAMPLE_FULL_YAML.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, {}, ""

    top_matches = list(_TOP_KEY_RE.finditer(text))
    top: dict[str, str] = {}
    for i, m in enumerate(top_matches):
        start = m.start()
        end = top_matches[i + 1].start() if i + 1 < len(top_matches) else len(text)
        top[m.group(1)] = text[start:end].rstrip() + "\n"

    annex: dict[str, str] = {}
    annex_matches = list(_ANNEX_ENTRY_RE.finditer(text))
    for i, m in enumerate(annex_matches):
        start = m.start()
        if i + 1 < len(annex_matches):
            end = annex_matches[i + 1].start()
        else:
            tail = text[start:]
            outdent = _OUTDENT_RE.search(tail)
            end = start + outdent.start() + 1 if outdent else len(text)
        annex[m.group(2)] = text[start:end].rstrip() + "\n"
    return top, annex, text


# ---------------------------------------------------------------------------
# Type formatting
# ---------------------------------------------------------------------------
def _fmt_type(annotation: Any) -> str:
    """Render a Pydantic/typing annotation as a short human-readable string."""
    origin = get_origin(annotation)
    args = get_args(annotation)

    if annotation is type(None):
        return "None"
    if origin is None:
        if hasattr(annotation, "__name__"):
            return annotation.__name__
        return str(annotation).replace("typing.", "")

    if origin is list:
        return f"list[{_fmt_type(args[0])}]" if args else "list"
    if origin is dict:
        return f"dict[{_fmt_type(args[0])}, {_fmt_type(args[1])}]" if len(args) == 2 else "dict"
    if origin in (typing.Union, types.UnionType):
        parts = [_fmt_type(a) for a in args if a is not type(None)]
        has_none = any(a is type(None) for a in args)
        inner = " | ".join(parts)
        return f"Optional[{inner}]" if has_none else inner
    if origin is typing.Literal:
        return "Literal[" + ", ".join(repr(a) for a in args) + "]"
    if origin is typing.Annotated:
        return _fmt_type(args[0])
    return str(annotation).replace("typing.", "")


def _doc(cls: type) -> str:
    return (cls.__doc__ or "").strip()


# ---------------------------------------------------------------------------
# Collect annex models + shared sub-types touched by them
# ---------------------------------------------------------------------------
def _annex_models() -> dict[str, type[BaseModel]]:
    """letter → AnnexXData class, in canonical A–Z order."""
    out: dict[str, type[BaseModel]] = {}
    for model in get_args(get_args(AnnexTypedBody)[0]):
        out[literal_value(model.model_fields["letter"])] = model
    return dict(sorted(out.items()))


def _referenced_submodels(models: list[type[BaseModel]]) -> dict[str, type[BaseModel]]:
    """Walk the fields of the given annex models and collect every Pydantic
    sub-model they reference (for a shared-types section)."""
    seen: dict[str, type[BaseModel]] = {}
    root_names = {m.__name__ for m in models}

    def visit(annotation: Any) -> None:
        origin = get_origin(annotation)
        args = get_args(annotation)
        if origin in (list, dict, typing.Union, types.UnionType, typing.Annotated, typing.Literal):
            for a in args:
                visit(a)
            return
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            if annotation.__name__ not in seen and annotation.__name__ not in root_names:
                seen[annotation.__name__] = annotation
                for f in annotation.model_fields.values():
                    visit(f.annotation)

    for m in models:
        for f in m.model_fields.values():
            visit(f.annotation)
    return dict(sorted(seen.items()))


# ---------------------------------------------------------------------------
# HTML emission
# ---------------------------------------------------------------------------
CSS = """
:root {
  --ink: #0f172a; --ink-soft: #1e293b; --ink-mute: #475569; --ink-low: #64748b;
  --rule: #e2e8f0; --rule-soft: #f1f5f9; --chip: #f8fafc;
  --accent: #c2410c; --accent-deep: #7c2d12; --accent-warm: #f59e0b;
  --accent-peach: #fed7aa;
}
* { box-sizing: border-box; }
html, body {
  margin: 0; padding: 0; background: #ffffff; color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
               "Helvetica Neue", Arial, sans-serif;
  font-size: 15px; line-height: 1.55;
  text-rendering: optimizeSpeed;
}
.mono, code {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas,
               "Liberation Mono", monospace;
}

/* Perf: defer off-screen rendering of expensive sections.
   Modern browsers skip layout/paint for unseen content, huge wins on
   long reference pages. Fallback: fully visible on older browsers. */
section.annex,
.sub-model,
.appendix-block {
  content-visibility: auto;
  contain-intrinsic-size: auto 800px;
}
section.annex { contain: layout paint style; }

.page { max-width: 1100px; margin: 0 auto; padding: 32px 40px 64px; }
header.cover {
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 55%, #334155 100%);
  color: #fff; padding: 32px 40px; margin: 0 -40px 32px -40px; border-radius: 0 0 18px 18px;
}
header.cover .eyebrow {
  font-family: "JetBrains Mono", monospace; font-size: 11px; font-weight: 600;
  letter-spacing: 0.2em; text-transform: uppercase; color: var(--accent-warm);
}
header.cover h1 {
  font-size: 36px; font-weight: 800; letter-spacing: -0.02em; margin: 6px 0 0 0;
}
header.cover .subtitle {
  color: #cbd5e1; font-size: 14px; margin-top: 10px; max-width: 720px;
}
nav.toc {
  background: var(--chip); border: 1px solid var(--rule); border-radius: 12px;
  padding: 16px 20px; margin-bottom: 32px;
}
nav.toc h2 {
  font-size: 11px; letter-spacing: 0.16em; text-transform: uppercase;
  color: var(--accent); margin: 0 0 10px 0;
}
nav.toc ul { list-style: none; padding: 0; margin: 0; display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 4px 12px; }
nav.toc a { color: var(--ink-soft); text-decoration: none; font-size: 14px; }
nav.toc a .letter {
  display: inline-block; width: 22px; font-family: "JetBrains Mono", monospace;
  font-weight: 700; color: var(--accent);
}
nav.toc a:hover { color: var(--accent-deep); }
nav.toc a.reserved { color: var(--ink-low); }
nav.toc a.reserved .letter { color: var(--ink-low); }

section.annex {
  margin: 40px 0; padding: 0; scroll-margin-top: 20px;
}
section.annex h2 {
  font-size: 26px; font-weight: 800; letter-spacing: -0.015em; margin: 0 0 4px 0;
  display: flex; align-items: baseline; gap: 14px;
}
section.annex h2 .letter-badge {
  display: inline-block; font-family: "JetBrains Mono", monospace;
  font-weight: 800; font-size: 20px; color: #fff;
  width: 38px; height: 38px; line-height: 38px; text-align: center;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-deep) 100%);
  flex: 0 0 auto;
}
section.annex h2 .structural-badge {
  font-size: 14px;
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  letter-spacing: 0.04em;
}
section.annex.structural .nested-models {
  margin: 28px 0 0 52px;
  padding: 18px 22px;
  background: var(--rule-soft);
  border-radius: 10px;
  border-left: 3px solid var(--accent);
}
section.annex.structural .nested-models > .sub-model:first-child { margin-top: 0; }
section.annex.structural .nested-models .sub-model { margin: 20px 0; padding: 0; }
section.annex.structural .nested-models .sub-model h3 {
  font-size: 15px; font-weight: 700; margin: 0 0 4px 0;
  font-family: "JetBrains Mono", monospace; color: var(--accent-deep);
}
section.annex.structural .nested-models .sub-model .description {
  color: var(--ink-mute); font-size: 13.5px; margin: 0 0 10px 52px;
  max-width: 820px;
}
section.annex.structural .nested-models .sub-model > .description { margin-left: 0; }
section.annex.structural .nested-models table.fields { margin-left: 0; width: 100%; }
section.annex .doctrine-ref {
  font-size: 13px; color: var(--ink-low); margin: 0 0 16px 52px;
}
section.annex .description {
  color: var(--ink-soft); margin: 0 0 20px 52px; max-width: 820px;
}

h3.subhead {
  font-size: 13px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--accent); margin: 22px 0 8px 52px;
  padding-bottom: 4px; border-bottom: 1.5px solid var(--accent-peach);
  max-width: calc(100% - 52px);
}
h3.subhead code {
  font-size: 12px; text-transform: none; letter-spacing: 0;
  background: var(--accent-peach); color: var(--accent-deep);
  padding: 1px 6px; border-radius: 3px;
}

table.fields {
  width: 100%; border-collapse: collapse; margin-left: 52px; width: calc(100% - 52px);
  font-size: 13.5px;
}
table.fields thead th {
  font-family: "JetBrains Mono", monospace; font-size: 11px; font-weight: 700;
  letter-spacing: 0.12em; text-transform: uppercase; color: var(--ink-low);
  text-align: left; padding: 8px 10px; border-bottom: 2px solid var(--accent);
  background: var(--chip);
}
table.fields tbody tr { border-bottom: 1px solid var(--rule-soft); }
table.fields tbody td { padding: 10px; vertical-align: top; }
table.fields tbody td.name {
  font-family: "JetBrains Mono", monospace; font-weight: 600;
  color: var(--accent-deep); white-space: nowrap;
}
table.fields tbody td.type {
  font-family: "JetBrains Mono", monospace; font-size: 12.5px;
  color: var(--ink-mute); white-space: nowrap;
}
table.fields tbody td.req .badge {
  display: inline-block; font-family: "JetBrains Mono", monospace;
  font-size: 10px; font-weight: 700; letter-spacing: 0.12em;
  padding: 2px 7px; border-radius: 4px; text-transform: uppercase;
}
table.fields tbody td.req .badge.required { background: #fee2e2; color: #991b1b; }
table.fields tbody td.req .badge.optional { background: var(--chip); color: var(--ink-low); }
table.fields tbody td.desc { color: var(--ink-soft); }

.reserved-note {
  padding: 10px 16px; background: var(--chip); border-left: 3px solid var(--ink-low);
  border-radius: 0 8px 8px 0; color: var(--ink-mute); font-size: 13px;
  margin-left: 52px;
}

.example-block {
  margin: 22px 0 0 52px;
  background: #0f172a;
  border-radius: 10px;
  overflow: hidden;
  border-left: 3px solid var(--accent-warm);
}
.example-block .example-head {
  background: linear-gradient(90deg, #0f172a 0%, #1e293b 100%);
  color: #e2e8f0;
  padding: 8px 14px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
.example-block .example-head .ex-label { color: var(--accent-warm); }
.example-block .example-head .ex-source { color: #94a3b8; font-weight: 500; text-transform: none; letter-spacing: 0; }
.example-block pre {
  margin: 0;
  padding: 14px 16px;
  background: #0f172a;
  color: #e2e8f0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11.5px;
  line-height: 1.55;
  overflow-x: auto;
  max-height: 480px;
  overflow-y: auto;
}
.example-block pre code { color: inherit; font-family: inherit; background: none; }

.appendices {
  margin: 28px 0 0 52px; padding: 16px 20px; background: var(--rule-soft, #f8fafc);
  border-radius: 10px; border-left: 3px solid var(--accent-warm);
}
.appendices h3 {
  font-size: 13px; letter-spacing: 0.14em; text-transform: uppercase;
  color: var(--accent); margin: 0 0 14px 0;
  font-family: "JetBrains Mono", monospace;
}
.appendix-block {
  margin: 14px 0; padding: 14px 16px; background: #fff;
  border: 1px solid var(--rule); border-radius: 8px;
}
.appendix-block h4 {
  font-size: 16px; font-weight: 700; margin: 0 0 4px 0;
  display: flex; align-items: baseline; gap: 10px;
}
.appendix-block h4 .app-badge {
  font-family: "JetBrains Mono", monospace; font-size: 10px; font-weight: 700;
  letter-spacing: 0.12em; padding: 2px 8px; border-radius: 4px;
  background: var(--accent-peach); color: var(--accent-deep);
}
.appendix-block .purpose {
  color: var(--ink-mute); font-size: 13px; margin: 0 0 8px 0; max-width: 780px;
}
.appendix-block .doctrine-cite {
  font-family: "JetBrains Mono", monospace; font-size: 10px;
  color: var(--ink-low); margin: 0 0 10px 0;
  letter-spacing: 0.04em;
}
.appendix-block table.fields { margin-left: 0; width: 100%; }
.no-appendices {
  font-size: 13px; color: var(--ink-low); font-style: italic;
  padding: 8px 0 0 0;
}

.shared-types { margin-top: 56px; padding-top: 24px; border-top: 2px solid var(--rule); }
.shared-types h2 { font-size: 22px; font-weight: 800; letter-spacing: -0.01em; }
.shared-types .sub-model { margin: 24px 0; padding: 0; }
.shared-types .sub-model h3 {
  font-size: 16px; font-weight: 700; margin: 0 0 4px 0;
  font-family: "JetBrains Mono", monospace; color: var(--accent-deep);
}
.shared-types .sub-model .description {
  color: var(--ink-mute); font-size: 13.5px; margin: 0 0 10px 0;
}
.shared-types table.fields { margin-left: 0; width: 100%; }

h2.toc-group-head { margin-top: 18px; }
table.fields.indented { margin-left: 52px; width: calc(100% - 52px); }
p.description.indented { margin-left: 52px; }
.letter-badge.reserved { background: linear-gradient(135deg, #64748b 0%, #334155 100%); }
.field-default { color: var(--ink-low); }
.shared-types-intro { color: var(--ink-mute); max-width: 820px; }

footer {
  margin-top: 48px; padding-top: 20px; border-top: 1px solid var(--rule);
  color: var(--ink-low); font-size: 12px; text-align: center;
}
"""


_FIELDS_TABLE_HEAD = (
    '<table class="fields"><thead><tr>'
    '<th>Field</th><th>Type</th><th>Req</th><th>Description</th>'
    '</tr></thead>'
)


def _req_badge(required: bool) -> str:
    return (
        '<span class="badge required">Required</span>' if required
        else '<span class="badge optional">Optional</span>'
    )


def _fields_table(rows: list[str]) -> str:
    return f'{_FIELDS_TABLE_HEAD}<tbody>{"".join(rows)}</tbody></table>'


def _render_field_row(name: str, field: FieldInfo) -> str:
    type_str = _fmt_type(field.annotation)
    req = field.is_required()
    desc = field.description or ""
    default = ""
    if not req and field.default not in (None, Ellipsis):
        if field.default_factory is None:
            default = f" <span class=\"mono field-default\">default: {escape(repr(field.default))}</span>"
    return (
        f'<tr><td class="name">{escape(name)}</td>'
        f'<td class="type"><code>{escape(type_str)}</code></td>'
        f'<td class="req">{_req_badge(req)}</td>'
        f'<td class="desc">{escape(desc)}{default}</td></tr>'
    )


def _render_appendix_block(letter: str) -> str:
    """Render the appendix catalog block for an annex letter, if present."""
    specs = APPENDIX_CATALOG.get(letter) if APPENDIX_CATALOG else None
    if specs is None:
        return ""
    if not specs:
        return (
            '<div class="appendices">'
            '<h3>Appendices</h3>'
            '<div class="no-appendices">This annex has no doctrinal appendices per FM 6-0 (May 2022).</div>'
            '</div>'
        )

    parts: list[str] = ['<div class="appendices"><h3>Appendices</h3>']
    for spec in specs:
        parts.append('<div class="appendix-block">')
        parts.append(
            f'<h4><span class="app-badge">APP {spec.number} ({letter})</span>'
            f'{escape(spec.title)}</h4>'
        )
        if spec.purpose:
            parts.append(f'<p class="purpose">{escape(spec.purpose)}</p>')
        if spec.doctrine_reference:
            parts.append(f'<div class="doctrine-cite">{escape(spec.doctrine_reference)}</div>')
        if spec.fields:
            rows = [
                f'<tr><td class="name">{escape(f.name)}</td>'
                f'<td class="type"><code>{escape(f.type_hint)}</code></td>'
                f'<td class="req">{_req_badge(f.required)}</td>'
                f'<td class="desc">{escape(f.description)}</td></tr>'
                for f in spec.fields
            ]
            parts.append(_fields_table(rows))
        parts.append('</div>')
    parts.append('</div>')
    return "".join(parts)


def _render_model_table(model: type[BaseModel], skip_fields: set[str] | None = None) -> str:
    skip_fields = skip_fields or set()
    rows = [
        _render_field_row(name, field)
        for name, field in model.model_fields.items()
        if name not in skip_fields
    ]
    return _fields_table(rows)


def _render_example_block(key: str, examples: dict[str, str]) -> str:
    """Render the live-YAML panel for a given examples[] key.

    ``key`` may be an annex letter (A–Z) or any top-level OPORD key
    (header, situation, mission, execution, sustainment, command_and_signal,
    authentication).
    """
    snippet = examples.get(key)
    if not snippet:
        return ""
    return (
        '<div class="example-block">'
        '<div class="example-head">'
        '<span class="ex-label">IRON STRIKE — LIVE YAML</span>'
        '<span class="ex-source">examples/example_full.yaml</span>'
        '</div>'
        f'<pre><code>{escape(snippet)}</code></pre>'
        '</div>'
    )


def _render_sub_model(cls: type[BaseModel], skip_fields: set[str] | None = None) -> str:
    """Render a nested sub-model as its own heading + field table, matching
    the ``.sub-model`` style used in the shared-types appendix."""
    doc = _doc(cls)
    parts = ['<div class="sub-model">']
    parts.append(f'<h3>{escape(cls.__name__)}</h3>')
    if doc:
        parts.append(f'<p class="description">{escape(doc)}</p>')
    parts.append(_render_model_table(cls, skip_fields=skip_fields))
    parts.append('</div>')
    return "".join(parts)


def _render_structural_section(
    *,
    slug: str,
    badge: str,
    heading: str,
    doc: str | None,
    parent: type[BaseModel] | None,
    nested: list[type[BaseModel]] | None = None,
    example_key: str | None = None,
    examples: dict[str, str] | None = None,
    skip_parent_fields: set[str] | None = None,
) -> str:
    """Emit a full ``<section class="annex structural">`` block for a
    top-level OPORD structural element (Header, Situation, Execution, …).

    Reuses the same CSS as the per-annex sections but swaps the letter
    badge for a short symbolic / numeric badge.
    """
    parts: list[str] = [f'<section class="annex structural" id="section-{slug}">']
    parts.append(
        f'<h2><span class="letter-badge structural-badge">{escape(badge)}</span>{escape(heading)}</h2>'
    )
    if doc:
        parts.append(f'<p class="description">{escape(doc)}</p>')
    if parent is not None:
        parts.append(_render_model_table(parent, skip_fields=skip_parent_fields))
    if nested:
        parts.append('<div class="nested-models">')
        for sub in nested:
            parts.append(_render_sub_model(sub))
        parts.append('</div>')
    if example_key and examples is not None:
        parts.append(_render_example_block(example_key, examples))
    parts.append('</section>')
    return "".join(parts)


def generate_html() -> str:
    annexes = _annex_models()
    shared = _referenced_submodels(list(annexes.values()))
    top_level, examples, raw_yaml = _load_example_full()

    # Cover
    out: list[str] = [
        "<!DOCTYPE html><html lang=\"en\"><head>",
        "<meta charset=\"UTF-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<title>OPORD Schema Reference</title>",
        f"<style>{CSS}</style>",
        "</head><body><div class=\"page\">",
        "<header class=\"cover\">",
        "<div class=\"eyebrow\">Schema Reference</div>",
        "<h1>OPORD Schema Reference</h1>",
        "<p class=\"subtitle\">Field-by-field documentation of the complete OPORD schema: top-level structure (header, five paragraphs, authentication), the generic Annex/Appendix container, and every annex letter A–Z with its doctrinally-prescribed <code>typed_body</code> per FM 6-0 (May 2022) Appendix D and ATP 5-0.2-1. Reserved letters (I, O, T, W, X, Y) are not assignable. &nbsp;<a href=\"tree.html\" style=\"color: #fed7aa; text-decoration: underline;\">Raw JSON-Schema tree →</a></p>",
        "</header>",
    ]

    # Structural sections that appear before the per-annex pages.
    structural_toc: list[tuple[str, str, str]] = [
        ("opord", "§", "OPORD — Top-Level Structure"),
        ("header", "§", "Header"),
        ("situation", "1", "Paragraph 1 — Situation"),
        ("mission", "2", "Paragraph 2 — Mission"),
        ("execution", "3", "Paragraph 3 — Execution"),
        ("sustainment", "4", "Paragraph 4 — Sustainment"),
        ("command-and-signal", "5", "Paragraph 5 — Command and Signal"),
        ("annex-container", "A/n", "Annex Container (Generic)"),
    ]

    # TOC
    out.append('<nav class="toc"><h2>Schema Index</h2><ul>')
    for slug, badge, heading in structural_toc:
        out.append(
            f'<li><a href="#section-{slug}"><span class="letter">{escape(badge)}</span>{escape(heading)}</a></li>'
        )
    out.append(
        '<li><a href="#section-authentication"><span class="letter">§</span>Authentication</a></li>'
    )
    out.append("</ul>")
    out.append('<h2 class="toc-group-head">Annex Index</h2><ul>')
    for letter, title in CANONICAL_ANNEXES.items():
        if letter in RESERVED_LETTERS:
            out.append(
                f'<li><a class="reserved" href="#annex-{letter}"><span class="letter">{letter}</span>Not Used</a></li>'
            )
        else:
            out.append(
                f'<li><a href="#annex-{letter}"><span class="letter">{letter}</span>{escape(title)}</a></li>'
            )
    out.append("</ul></nav>")

    # -----------------------------------------------------------------
    # Top-level OPORD structure (precedes the per-annex loop).
    # -----------------------------------------------------------------

    # 1. OPORD top-level shape — preview first ~30 lines of the live YAML
    opord_preview = "".join(raw_yaml.splitlines(keepends=True)[:30]) if raw_yaml else ""
    opord_examples = {"opord": opord_preview} if opord_preview else {}
    out.append(_render_structural_section(
        slug="opord",
        badge="§",
        heading="OPORD — Top-Level Structure",
        doc=_doc(OPORD),
        parent=OPORD,
        nested=None,
        example_key="opord" if opord_preview else None,
        examples=opord_examples,
    ))

    # 2. Header
    out.append(_render_structural_section(
        slug="header",
        badge="§",
        heading="Header",
        doc=_doc(Header),
        parent=Header,
        nested=[Reference, Unit],
        example_key="header",
        examples=top_level,
    ))

    # 3. Paragraph 1 — Situation
    out.append(_render_structural_section(
        slug="situation",
        badge="1",
        heading="Paragraph 1 — Situation",
        doc=_doc(Situation),
        parent=Situation,
        nested=[
            AreaOfOperations,
            Terrain,
            Weather,
            EnemyForces,
            HigherHeadquarters,
            FriendlyForces,
            CivilConsiderations,
            AttachmentsDetachments,
        ],
        example_key="situation",
        examples=top_level,
    ))

    # 4. Paragraph 2 — Mission (bare string on the OPORD model)
    out.append('<section class="annex structural" id="section-mission">')
    out.append(
        '<h2><span class="letter-badge structural-badge">2</span>Paragraph 2 — Mission</h2>'
    )
    out.append(
        '<p class="description">Paragraph 2 is a single-sentence string on the '
        '<code>OPORD</code> model — no nested structure. Per FM 6-0 it answers '
        "who, what (task), when, where, and why (purpose). Required; cannot be omitted.</p>"
    )
    out.append(
        '<table class="fields indented">'
        '<thead><tr><th>Field</th><th>Type</th><th>Req</th><th>Description</th></tr></thead>'
        '<tbody>' + _render_field_row("mission", OPORD.model_fields["mission"]) + '</tbody></table>'
    )
    out.append(_render_example_block("mission", top_level))
    out.append('</section>')

    # 5. Paragraph 3 — Execution
    out.append(_render_structural_section(
        slug="execution",
        badge="3",
        heading="Paragraph 3 — Execution",
        doc=_doc(Execution),
        parent=Execution,
        nested=[
            CommandersIntent,
            ConceptOfOperations,
            SubordinateTask,
            CCIR,
            CoordinatingInstructions,
        ],
        example_key="execution",
        examples=top_level,
    ))

    # 6. Paragraph 4 — Sustainment
    out.append(_render_structural_section(
        slug="sustainment",
        badge="4",
        heading="Paragraph 4 — Sustainment",
        doc=_doc(Sustainment),
        parent=Sustainment,
        nested=[Logistics, PersonnelServices, HealthServices],
        example_key="sustainment",
        examples=top_level,
    ))

    # 7. Paragraph 5 — Command and Signal
    out.append(_render_structural_section(
        slug="command-and-signal",
        badge="5",
        heading="Paragraph 5 — Command and Signal",
        doc=_doc(CommandAndSignal),
        parent=CommandAndSignal,
        nested=[Command, Control, Signal],
        example_key="command_and_signal",
        examples=top_level,
    ))

    # 8. Annex container (generic) — shared across every annex letter.
    annex_container_intro = (
        "Every annex entry in <code>annexes:</code> is an "
        "<code>Annex</code>. These generic container fields (letter, title, "
        "status, body, appendices, distribution_list, call_sign_groups) coexist "
        "with the per-annex <code>typed_body</code> documented below — the "
        "container carries the prose, appendices, callsign rosters, and "
        "distribution; the typed_body carries the annex-specific doctrinal "
        "fields (e.g. collection plan for Annex L, priority intelligence for "
        "Annex B). An Appendix can additionally carry frequency tables "
        "(radio ladders) — most commonly under Annex H, Appendix 1."
    )
    out.append('<section class="annex structural" id="section-annex-container">')
    out.append(
        '<h2><span class="letter-badge structural-badge">A/n</span>Annex Container (Generic)</h2>'
    )
    out.append(f'<p class="description">{annex_container_intro}</p>')
    # Parent Annex model table (keep letter since it's a user-set discriminator)
    out.append(_render_model_table(Annex))
    out.append('<div class="nested-models">')
    out.append(_render_sub_model(Appendix))
    out.append(_render_sub_model(CallSignGroup))
    out.append(_render_sub_model(CallSignEntry))
    out.append(_render_sub_model(FrequencyTable))
    out.append(_render_sub_model(FrequencyChannel))
    out.append('</div>')
    out.append('</section>')

    # Cache the two per-annex tables that render identically every iteration
    # (their source models don't vary by annex letter).
    annex_container_table = _render_model_table(
        Annex, skip_fields={"letter", "title", "status", "typed_body"}
    )
    appendix_container_table = _render_model_table(Appendix)

    # Per-annex sections
    for letter, title in CANONICAL_ANNEXES.items():
        out.append(f'<section class="annex" id="annex-{letter}">')
        if letter in RESERVED_LETTERS:
            out.append(f'<h2><span class="letter-badge reserved">{letter}</span>Annex {letter} — Not Used</h2>')
            out.append(
                '<div class="reserved-note">Reserved letter per FM 6-0 (May 2022). '
                "Letters I and O are reserved to avoid confusion with numerals 1/0; "
                "T, W, X, and Y are held for future doctrinal use. "
                "These letters cannot be assigned in an OPORD.</div>"
            )
            out.append("</section>")
            continue

        cls = annexes.get(letter)
        if cls is None:
            out.append(f'<h2><span class="letter-badge">{letter}</span>Annex {letter} — {escape(title)}</h2>')
            out.append('<p class="description">No typed_body model defined for this annex.</p>')
            out.append("</section>")
            continue

        doc = _doc(cls)
        out.append(f'<h2><span class="letter-badge">{letter}</span>Annex {letter} — {escape(title)}</h2>')
        if doc:
            out.append(f'<p class="description">{escape(doc)}</p>')

        # Typed-body schema (annex-specific structured fields)
        out.append('<h3 class="subhead">Typed body (<code>typed_body</code>)</h3>')
        out.append(_render_model_table(cls, skip_fields={"letter"}))

        # Generic Annex container fields — where call_sign_groups, body,
        # distribution_list, and appendices live. These are SHARED by every
        # annex; users author them at the Annex level alongside typed_body.
        out.append(
            '<h3 class="subhead">Generic <code>Annex</code> container fields '
            '(also available on this annex)</h3>'
            '<p class="description indented">'
            'These fields live on the top-level <code>Annex</code> object next to '
            '<code>typed_body</code>. <code>call_sign_groups</code> holds the '
            'callsign roster; <code>appendices</code> is where radio ladders '
            'live (via each appendix\'s <code>frequency_tables</code> — see below).'
            '</p>'
        )
        out.append(annex_container_table)

        # Appendix container — specifically highlight frequency_tables for H
        out.append(
            '<h3 class="subhead"><code>Appendix</code> container '
            '(structure of every entry in <code>appendices</code>)</h3>'
        )
        out.append(appendix_container_table)

        if letter == "H":
            out.append(
                '<h3 class="subhead"><code>CallSignGroup</code> / <code>CallSignEntry</code> '
                '(callsign-roster sub-types)</h3>'
            )
            out.append(_render_sub_model(CallSignGroup))
            out.append(_render_sub_model(CallSignEntry))
            out.append(
                '<h3 class="subhead"><code>FrequencyTable</code> / <code>FrequencyChannel</code> '
                '(radio-ladder sub-types — used inside <code>Appendix.frequency_tables</code>)</h3>'
            )
            out.append(_render_sub_model(FrequencyTable))
            out.append(_render_sub_model(FrequencyChannel))

        # Live YAML from example_full.yaml
        out.append(_render_example_block(letter, examples))

        # Per-appendix breakdown from the doctrinal catalog
        out.append(_render_appendix_block(letter))

        out.append("</section>")

    # Authentication (trails the annexes, matches YAML ordering)
    out.append(_render_structural_section(
        slug="authentication",
        badge="§",
        heading="Authentication",
        doc=_doc(Authentication),
        parent=Authentication,
        nested=None,
        example_key="authentication",
        examples=top_level,
    ))

    # Shared types
    if shared:
        out.append('<div class="shared-types"><h2>Shared Sub-Types</h2>')
        out.append(
            '<p class="shared-types-intro">Reusable doctrine-true record types referenced across multiple annexes. '
            "Each is defined once and imported where needed.</p>"
        )
        for cls in shared.values():
            out.append(_render_sub_model(cls))
        out.append("</div>")

    out.append(
        "<footer>Generated from the live Pydantic schema. "
        "Run <code>uv run opord reference</code> to regenerate.</footer>"
    )
    out.append("</div></body></html>")
    return "".join(out)


def write_reference(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generate_html(), encoding="utf-8")
    return path
