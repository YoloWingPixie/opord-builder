"""YAML → OPORD → Markdown + PDF rendering pipeline."""

from __future__ import annotations

import base64
import re
import urllib.error
import urllib.request
import warnings
from datetime import datetime, timezone
from functools import lru_cache
from html import escape
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, TypeVar

import yaml
from jinja2 import DebugUndefined, Environment, FileSystemLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel

_M = TypeVar("_M", bound=BaseModel)

if TYPE_CHECKING:
    from weasyprint import CSS as _WeasyCSS

from opord_builder._paths import STYLESHEET, TEMPLATES_DIR
from opord_builder.schema import FRAGO, OPORD, WARNO, CANONICAL_ANNEXES, RESERVED_LETTERS
from opord_builder.schema._base import literal_value

_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
_IMG_SUFFIXES = (".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif")

_WATERMARK_ACCENT = "#0b3d91"
_WATERMARK_ALPHA = 0.10
_WATERMARK_MAX_DIM = 1200        # px — cap source before embedding to keep HTML small
_WATERMARK_FETCH_TIMEOUT = 5     # s
_WATERMARK_MAX_BYTES = 2 * 1024 * 1024  # 2 MiB cap on fetched image bytes


def _is_image_watermark(value: str) -> bool:
    v = value.lower()
    return v.startswith(("http://", "https://")) or v.endswith(_IMG_SUFFIXES)


@lru_cache(maxsize=2)
def _fade_image_data_url(source: str) -> str:
    """Download + alpha-fade + base64 once per render (same watermark reused
    on every page). Separated from the SVG path so PIL is only imported when
    an image watermark is actually used."""
    from PIL import Image

    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=_WATERMARK_FETCH_TIMEOUT) as resp:
            img_bytes = resp.read(_WATERMARK_MAX_BYTES + 1)
            if len(img_bytes) > _WATERMARK_MAX_BYTES:
                raise ValueError(f"watermark image exceeds {_WATERMARK_MAX_BYTES} bytes")
    else:
        img_bytes = Path(source).read_bytes()

    img = Image.open(BytesIO(img_bytes)).convert("RGBA")
    img.thumbnail((_WATERMARK_MAX_DIM, _WATERMARK_MAX_DIM))
    lut = [int(i * _WATERMARK_ALPHA) for i in range(256)]
    img.putalpha(img.split()[3].point(lut))
    out = BytesIO()
    img.save(out, "PNG", optimize=True)
    return f"data:image/png;base64,{base64.b64encode(out.getvalue()).decode('ascii')}"


def _text_watermark_svg(text: str) -> str:
    escaped = escape(text, quote=True)
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='900' height='500' "
        "viewBox='0 0 900 500'>"
        f"<text x='450' y='300' text-anchor='middle' "
        f"font-family='Helvetica,Arial,sans-serif' font-size='180' "
        f"font-weight='800' fill='{_WATERMARK_ACCENT}' opacity='{_WATERMARK_ALPHA}' "
        f"transform='rotate(-28 450 250)'>{escaped}</text>"
        "</svg>"
    )
    return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode('utf-8')).decode('ascii')}"


def _watermark_from_value(wm: str | None) -> str:
    if not wm:
        return ""
    if _is_image_watermark(wm):
        try:
            return _fade_image_data_url(wm)
        except (OSError, urllib.error.URLError, ValueError, ImportError) as exc:
            warnings.warn(f"watermark fade failed ({exc!r}); embedding raw URL", stacklevel=2)
            return wm
    return _text_watermark_svg(wm)


def _resolve_watermark(opord: OPORD) -> str:
    return _watermark_from_value(opord.header.watermark)


@lru_cache(maxsize=1)
def _stylesheet_text() -> str:
    return STYLESHEET.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Emptiness detection — the heart of "no blank sections render"
# ---------------------------------------------------------------------------
def has_content(value: Any) -> bool:
    """True iff ``value`` has any non-empty descendant content.

    Rules:
      - None, empty string, empty list/tuple/set/dict → False.
      - Pydantic model → True iff any field has content (recursive).
      - Everything else → ``bool(value)``.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set)):
        return any(has_content(v) for v in value)
    if isinstance(value, dict):
        return any(has_content(v) for v in value.values())
    if isinstance(value, BaseModel):
        return any(has_content(getattr(value, name)) for name in value.__class__.model_fields)
    return bool(value)


# ---------------------------------------------------------------------------
# Small letter/numeral helpers for doctrinal numbering (a., b., (1), (a))
# ---------------------------------------------------------------------------
_LOWER = "abcdefghijklmnopqrstuvwxyz"


@lru_cache(maxsize=128)
def letter_for(n: int) -> str:
    """1→a, 2→b, ... 26→z, 27→aa, ..."""
    if n <= 0:
        return ""
    out = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        out = _LOWER[r] + out
    return out


# ---------------------------------------------------------------------------
# Environment factory
# ---------------------------------------------------------------------------
_ACRONYMS: frozenset[str] = frozenset({
    "ccir", "pir", "hvt", "dtg", "mgrs", "sofa", "soi", "msr", "asr",
    "nfa", "cfl", "roz", "fscm", "agm", "hptl", "moe", "mop", "uas",
    "isr", "pr", "cbrn", "eod", "opsec", "fhp", "at", "ig", "km",
    "pa", "satcom", "axp", "ctcp", "bsa", "bn", "bct", "hn", "lno",
    "coa", "mlcoa", "mdcoa", "nai", "tai", "ltiov", "cal", "dal",
    "hns", "cmo", "cmoc", "pace", "comsec", "nco", "ncoic", "po",
    "ppc",
})


@lru_cache(maxsize=512)
def _humanize(name: str) -> str:
    """snake_case → Title Case; tokens in _ACRONYMS stay uppercase."""
    parts = name.replace("_", " ").split()
    return " ".join(p.upper() if p.lower() in _ACRONYMS else p.capitalize() for p in parts)


def _union_columns(items: list) -> list[str]:
    """Collect the ordered union of Pydantic field names across a heterogeneous list."""
    cols: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, BaseModel):
            continue
        for f in item.__class__.model_fields:
            if f not in seen:
                seen.add(f)
                cols.append(f)
    return cols


def render_typed_body_html(typed_body) -> str:
    """Render a per-annex typed_body Pydantic model to a standalone HTML block.

    Top-level fields are auto-numbered (1., 2., 3., ...) as annex paragraphs.
    Nested models render without numbering.

    Fields render as:
      - str → <p> paragraphs (split on blank lines)
      - list[str] → <ul> bullets
      - list[BaseModel] → <table> with columns from the sub-model's fields
      - BaseModel → nested key/value block
      - int/bool/enum → inline key/value row
    Empty fields are omitted.
    """
    if typed_body is None:
        return ""
    return _render_model_html(typed_body, skip_fields={"letter"}, numbered=True)


def _render_model_html(model, skip_fields: set[str] | None = None, numbered: bool = False) -> str:
    skip_fields = skip_fields or set()
    parts: list[str] = ['<div class="typed-body">']
    idx = 0
    for field_name in model.__class__.model_fields:
        if field_name in skip_fields:
            continue
        value = getattr(model, field_name, None)
        if not has_content(value):
            continue
        idx += 1
        base_label = escape(_humanize(field_name))
        label = (
            f'<span class="tb-num">{idx}.</span> {base_label}'
            if numbered else base_label
        )
        if isinstance(value, str):
            paras = _split_paragraphs(value)
            body = "".join(f"<p>{escape(p)}</p>" for p in paras)
            parts.append(
                f'<div class="tb-field"><div class="tb-field-label">{label}</div><div class="tb-field-body">{body}</div></div>'
            )
        elif isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, BaseModel):
                parts.append(_render_list_of_models_html(label, value))
            else:
                items = "".join(f"<li>{escape(str(v))}</li>" for v in value if has_content(v))
                parts.append(
                    f'<div class="tb-field"><div class="tb-field-label">{label}</div><ul class="tb-list">{items}</ul></div>'
                )
        elif isinstance(value, BaseModel):
            # Nested model — render full-width with label above (same pattern
            # as list-of-models) so its own tables don't get squeezed into
            # the narrow 1fr track of the .tb-field grid.
            inner = _render_model_html(value)
            parts.append(
                f'<div class="tb-table-block"><div class="tb-field-label">{label}</div>{inner}</div>'
            )
        else:
            parts.append(
                f'<div class="tb-kv"><span class="tb-kv-k">{label}:</span> <span class="tb-kv-v">{escape(str(value))}</span></div>'
            )
    parts.append("</div>")
    return "".join(parts)


# Models with too many columns to render cleanly as a single PDF-width table.
# Values are summary field-name lists; everything else becomes a per-entry
# detail block rendered below the summary. See _render_split_list_html.
_SPLIT_RENDER: dict[str, dict[str, Any]] = {
    "JPITLEntry": {
        "summary": ["target_number", "priority_rank", "category", "desired_effect", "status"],
        "id_field": "target_number",
        "title_field": "target_name",
    },
    "TSTEntry": {
        "summary": ["tst_number", "priority_class", "category", "activity_window", "engagement_authority"],
        "id_field": "tst_number",
        "title_field": "target_description",
    },
    "NineLineCAS": {
        "summary": ["cas_callsign", "target_description", "ip_or_bp", "mark_type", "time_on_target"],
        "id_field": "cas_callsign",
        "title_field": "target_description",
    },
}


def _cell_html(value: Any) -> str:
    if not has_content(value):
        return ""
    if isinstance(value, list):
        if value and isinstance(value[0], BaseModel):
            return "<em>(nested)</em>"
        return "; ".join(escape(str(x)) for x in value)
    if isinstance(value, BaseModel):
        return "<em>(nested)</em>"
    return escape(str(value))


def _render_list_of_models_html(label: str, items: list) -> str:
    if items and isinstance(items[0], BaseModel):
        spec = _SPLIT_RENDER.get(items[0].__class__.__name__)
        if spec:
            return _render_split_list_html(label, items, spec)
    cols = _union_columns(items)
    header = "".join(f"<th>{escape(_humanize(c))}</th>" for c in cols)
    rows: list[str] = []
    for item in items:
        cells = "".join(f"<td>{_cell_html(getattr(item, c, None))}</td>" for c in cols)
        rows.append(f"<tr>{cells}</tr>")
    return (
        f'<div class="tb-table-block"><div class="tb-field-label">{label}</div>'
        f'<table class="tb-table"><thead><tr>{header}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def _render_split_list_html(label: str, items: list, spec: dict[str, Any]) -> str:
    """Summary table (few columns) + per-entry detail cards.
    For models too wide to table fully; drives JPITL / TST rendering."""
    summary_cols: list[str] = spec["summary"]
    id_field: str = spec["id_field"]
    title_field: str = spec["title_field"]

    # Summary table
    header = "".join(f"<th>{escape(_humanize(c))}</th>" for c in summary_cols)
    summary_rows: list[str] = []
    for item in items:
        cells = "".join(f"<td>{_cell_html(getattr(item, c, None))}</td>" for c in summary_cols)
        summary_rows.append(f"<tr>{cells}</tr>")

    # Per-entry detail blocks — every field NOT already in the summary.
    cls = items[0].__class__
    detail_fields = [f for f in cls.model_fields if f not in set(summary_cols)]
    details: list[str] = []
    for item in items:
        ident = escape(str(getattr(item, id_field, "") or ""))
        title = escape(str(getattr(item, title_field, "") or ""))
        head_html = f'<span class="tb-detail-id">{ident}</span>'
        if title:
            head_html += f'<span class="tb-detail-title">{title}</span>'
        rows_html: list[str] = []
        for f in detail_fields:
            v = getattr(item, f, None)
            if not has_content(v):
                continue
            rows_html.append(
                f'<div class="tb-detail-row">'
                f'<span class="tb-detail-k">{escape(_humanize(f))}</span>'
                f'<span class="tb-detail-v">{_cell_html(v)}</span>'
                f'</div>'
            )
        details.append(
            '<div class="tb-detail-entry">'
            f'<div class="tb-detail-head">{head_html}</div>'
            f'<div class="tb-detail-body">{"".join(rows_html)}</div>'
            '</div>'
        )

    return (
        f'<div class="tb-table-block"><div class="tb-field-label">{label}</div>'
        f'<table class="tb-table"><thead><tr>{header}</tr></thead>'
        f'<tbody>{"".join(summary_rows)}</tbody></table>'
        f'<div class="tb-detail-list">{"".join(details)}</div>'
        f'</div>'
    )


def _split_paragraphs(value: str | None) -> list[str]:
    """Split a multi-paragraph string on blank lines. Used to emit
    multiple <p> tags in HTML where the source text contains paragraph
    breaks (YAML block scalars with `|` or `>` often carry these)."""
    if not value:
        return []
    parts = _PARAGRAPH_SPLIT_RE.split(value.strip().replace("\r\n", "\n"))
    return [p.strip() for p in parts if p.strip()]


@lru_cache(maxsize=2)
def _make_env(html: bool) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "htm"]) if html else False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
        auto_reload=False,
        # HTML render only: wrap any surviving `{{ name }}` (undefined
        # variable reference) in a styled span so authors visibly spot typos.
        finalize=_wrap_undefined_html if html else None,
    )
    env.globals["has_content"] = has_content
    env.globals["letter_for"] = letter_for
    env.globals["CANONICAL_ANNEXES"] = CANONICAL_ANNEXES
    env.globals["RESERVED_LETTERS"] = RESERVED_LETTERS
    env.filters["paragraphs"] = _split_paragraphs
    env.globals["render_typed_body_html"] = render_typed_body_html
    env.globals["render_typed_body_md"] = render_typed_body_md
    return env


def render_typed_body_md(typed_body) -> str:
    """Render typed_body as GFM markdown (tables + bullets). Top-level annex
    fields get auto-numbered (1., 2., 3., ...) as annex paragraphs."""
    if typed_body is None:
        return ""
    return _render_model_md(typed_body, skip_fields={"letter"}, numbered=True)


def _render_model_md(model, skip_fields: set[str] | None = None, numbered: bool = False) -> str:
    skip_fields = skip_fields or set()
    parts: list[str] = []
    idx = 0
    for field_name in model.__class__.model_fields:
        if field_name in skip_fields:
            continue
        value = getattr(model, field_name, None)
        if not has_content(value):
            continue
        idx += 1
        base_label = _humanize(field_name)
        label = f"{idx}. {base_label}" if numbered else base_label
        if isinstance(value, str):
            parts.append(f"**{label}**\n\n{value}\n")
        elif isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, BaseModel):
                parts.append(_render_list_of_models_md(label, value))
            else:
                parts.append(f"**{label}**\n")
                for v in value:
                    if has_content(v):
                        parts.append(f"- {v}")
                parts.append("")
        elif isinstance(value, BaseModel):
            parts.append(f"**{label}**\n\n" + _render_model_md(value))
        else:
            parts.append(f"- **{label}:** {value}")
    return "\n".join(parts) + "\n"


def _cell_md(value: Any) -> str:
    if not has_content(value):
        return ""
    if isinstance(value, list):
        if value and isinstance(value[0], BaseModel):
            return "_(nested)_"
        return "; ".join(str(x) for x in value)
    if isinstance(value, BaseModel):
        return "_(nested)_"
    return str(value).replace("|", r"\|").replace("\n", " ")


def _render_list_of_models_md(label: str, items: list) -> str:
    if items and isinstance(items[0], BaseModel):
        spec = _SPLIT_RENDER.get(items[0].__class__.__name__)
        if spec:
            return _render_split_list_md(label, items, spec)
    cols = _union_columns(items)
    header = "| " + " | ".join(_humanize(c) for c in cols) + " |"
    divider = "|" + "|".join(["---"] * len(cols)) + "|"
    rows: list[str] = []
    for item in items:
        cells = [_cell_md(getattr(item, c, None)) for c in cols]
        rows.append("| " + " | ".join(cells) + " |")
    return f"\n**{label}**\n\n{header}\n{divider}\n" + "\n".join(rows) + "\n"


def _render_split_list_md(label: str, items: list, spec: dict[str, Any]) -> str:
    summary_cols: list[str] = spec["summary"]
    id_field: str = spec["id_field"]
    title_field: str = spec["title_field"]

    header = "| " + " | ".join(_humanize(c) for c in summary_cols) + " |"
    divider = "|" + "|".join(["---"] * len(summary_cols)) + "|"
    summary_rows: list[str] = []
    for item in items:
        cells = [_cell_md(getattr(item, c, None)) for c in summary_cols]
        summary_rows.append("| " + " | ".join(cells) + " |")

    cls = items[0].__class__
    detail_fields = [f for f in cls.model_fields if f not in set(summary_cols)]
    detail_blocks: list[str] = []
    for item in items:
        ident = str(getattr(item, id_field, "") or "")
        title = str(getattr(item, title_field, "") or "")
        head = f"**{ident}**" + (f" — {title}" if title else "")
        rows = []
        for f in detail_fields:
            v = getattr(item, f, None)
            if not has_content(v):
                continue
            rows.append(f"- **{_humanize(f)}:** {_cell_md(v)}")
        detail_blocks.append(head + "\n" + "\n".join(rows))

    return (
        f"\n**{label}**\n\n{header}\n{divider}\n"
        + "\n".join(summary_rows)
        + "\n\n"
        + "\n\n".join(detail_blocks)
        + "\n"
    )


# ---------------------------------------------------------------------------
# YAML loading with `!include <path>` support
# ---------------------------------------------------------------------------
# Lets authors split an OPORD across files — typically one file per annex —
# and include the fragments from the main YAML. Paths resolve relative to the
# file containing the !include tag, so nested includes work recursively.
class _IncludeLoader(yaml.SafeLoader):
    """SafeLoader with an ``!include <path>`` tag. The including file's
    directory is the base for relative paths. Use one-file-per-fragment:
    the tag substitutes whatever the target file parses to."""

    # Guards runaway recursion from malformed include chains. Real OPORDs
    # nest one or two levels deep; 16 leaves generous headroom without
    # letting a mistake spiral.
    _MAX_DEPTH = 16

    def __init__(self, stream):
        source = getattr(stream, "name", None)
        self._include_root = Path(source).parent if source else Path.cwd()
        self._include_stack: tuple[Path, ...] = ()
        super().__init__(stream)


def _construct_include(loader: _IncludeLoader, node: yaml.Node) -> Any:
    if not isinstance(node, yaml.ScalarNode):
        raise ValueError(
            f"!include requires a scalar path, got {type(node).__name__} "
            f"at {getattr(node, 'start_mark', 'unknown location')}"
        )
    rel = loader.construct_scalar(node)
    target = Path(rel)
    if not target.is_absolute():
        target = loader._include_root / target
    target = target.resolve()

    if target in loader._include_stack:
        cycle = " -> ".join(str(p) for p in (*loader._include_stack, target))
        raise ValueError(f"!include cycle detected: {cycle}")
    if len(loader._include_stack) >= _IncludeLoader._MAX_DEPTH:
        raise ValueError(f"!include nesting exceeds {_IncludeLoader._MAX_DEPTH} levels at {target}")

    parent = loader._include_stack[-1] if loader._include_stack else loader._include_root
    try:
        f = target.open("r", encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"!include {rel!r} from {parent}: {exc}") from exc
    try:
        sub_loader = _IncludeLoader(f)
        sub_loader._include_stack = (*loader._include_stack, target)
        try:
            data = sub_loader.get_single_data()
        finally:
            sub_loader.dispose()
    finally:
        f.close()
    return data


_IncludeLoader.add_constructor("!include", _construct_include)


# ---------------------------------------------------------------------------
# Variable substitution — `variables:` block at top of YAML gets Jinja-rendered
# into every string value before Pydantic validation. Keeps OPORDs DRY.
# Undefined names render literally (e.g. ``{{ typo_var }}`` stays in place)
# so authors see typos in the rendered document instead of a validation error;
# the renderer later wraps them in a styled span (see `_finalize_html`).
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _variables_env() -> Environment:
    # DebugUndefined re-emits `{{ name }}` for undefined references instead
    # of raising or rendering empty — see module comment above.
    return Environment(undefined=DebugUndefined, autoescape=False)


def _render_variables(data: Any, variables: dict[str, Any]) -> Any:
    env = _variables_env()
    cache: dict[str, Any] = {}

    def walk(node: Any) -> Any:
        if isinstance(node, str):
            if "{{" not in node and "{%" not in node:
                return node  # fast-path: no Jinja syntax, skip compile
            if node in cache:
                return cache[node]
            try:
                rendered = env.from_string(node).render(**variables)
            except Exception as exc:
                raise ValueError(
                    f"Variable render failed in {node!r}: {exc}"
                ) from exc
            cache[node] = rendered
            return rendered
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        return node

    return walk(data)


_UNDEFINED_VAR_RE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def _wrap_undefined_html(value: Any) -> Any:
    """Jinja finalize hook: wrap any surviving `{{ name }}` in a styled span
    so authors visually spot undefined variables in the rendered HTML/PDF.
    Preserves autoescape: escapes literal text, returns Markup for the span."""
    if not isinstance(value, str) or "{{" not in value:
        return value
    from markupsafe import Markup, escape as _html_escape
    parts = _UNDEFINED_VAR_RE.split(value)
    if len(parts) == 1:
        return value
    out: list[str] = [str(_html_escape(parts[0]))]
    for i in range(1, len(parts), 2):
        name = parts[i]
        tail = parts[i + 1] if i + 1 < len(parts) else ""
        out.append(
            f'<span class="undefined-var">{{{{ {_html_escape(name)} }}}}</span>'
        )
        out.append(str(_html_escape(tail)))
    return Markup("".join(out))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _is_simple_variable(value: Any) -> bool:
    """Variables must be scalars (str/int/float/bool/None) or nested dicts of
    scalars. Lists and rich objects are skipped because rendering them into a
    prose field would produce ugly repr output."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return True
    if isinstance(value, dict):
        return all(_is_simple_variable(v) for v in value.values())
    return False


def _sanitize_variables(variables: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for name, value in variables.items():
        if _is_simple_variable(value):
            clean[name] = value
        else:
            warnings.warn(
                f"variables.{name!r} skipped: variables must be scalar or nested "
                f"dict-of-scalars (got {type(value).__name__}); lists/models are "
                "not supported as variables.",
                stacklevel=3,
            )
    return clean


def _load_yaml_with_variables(
    yaml_path: Path | str,
    extra_vars: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Shared YAML front-end for load_opord_with_vars / _load_document_with_base:
    parse YAML (with `!include` resolution), strip + apply the `variables:`
    block, return the raw data structure ready for Pydantic validation.

    ``extra_vars`` is an implicit variable namespace merged into the
    interpolation context BEFORE the user's ``variables:`` block, so user
    values override implicit ones. Used by FRAGO loading to expose ``base``
    (the parent OPORD) as a variable in the FRAGO YAML.

    Returns ``(data, sanitized_user_vars)`` so callers that need the
    ``variables:`` dict (FRAGO/WARNO pulling base vars through) do not
    have to re-parse the file.
    """
    path = Path(yaml_path)
    with path.open("r", encoding="utf-8") as f:
        data = yaml.load(f, Loader=_IncludeLoader)
    if data is None:
        raise ValueError(f"{path} is empty or invalid YAML")
    if not isinstance(data, dict):
        return data, {}
    user_vars = data.pop("variables", None)
    effective: dict[str, Any] = dict(extra_vars) if extra_vars else {}
    sanitized: dict[str, Any] = {}
    if user_vars is not None:
        if not isinstance(user_vars, dict):
            raise ValueError(
                f"'variables:' block must be a mapping, got {type(user_vars).__name__}"
            )
        sanitized = _sanitize_variables(user_vars)
        effective.update(sanitized)
    if effective:
        data = _render_variables(data, effective)
    return data, sanitized


def load_opord_with_vars(yaml_path: Path | str) -> tuple[OPORD, dict[str, Any]]:
    """Load an OPORD and also return its sanitized ``variables:`` dict so
    delta-document loaders (FRAGO/WARNO) can pull those variables through
    as an implicit namespace without re-parsing the file."""
    data, user_vars = _load_yaml_with_variables(yaml_path)
    return OPORD.model_validate(data), user_vars


def load_opord(yaml_path: Path | str) -> OPORD:
    opord, _ = load_opord_with_vars(yaml_path)
    return opord


def _load_document_with_base(
    path: Path,
    *,
    model: type[_M],
) -> tuple[_M, OPORD | None]:
    """Shared loader for delta documents (FRAGO, WARNO) that may reference
    a base OPORD. Handles base_order resolution, base pull-through into the
    variable-interpolation namespace, and the optional-base standalone case.

    The expected ``kind:`` discriminator and whether ``base_order`` is
    required are both derived from ``model`` — the ``kind`` Literal value
    and the ``base_order`` field's required-ness live in the Pydantic
    schema already, so the caller only picks the model class.

    When ``base_order`` is set, the base is loaded exactly once (both the
    model and its ``variables:`` dict come back in a single parse) and is
    then exposed in the delta's variable-interpolation namespace as
    ``base`` / ``base_vars`` / every base variable merged flat (delta
    variables of the same name override)."""
    kind = literal_value(model.model_fields["kind"])
    base_required = model.model_fields["base_order"].is_required()
    with path.open("r", encoding="utf-8") as f:
        peek = yaml.load(f, Loader=_IncludeLoader)
    if not isinstance(peek, dict) or peek.get("kind") != kind:
        raise ValueError(
            f"{path} is not a {kind.upper()} — top-level 'kind: {kind}' required."
        )
    base_order = peek.get("base_order")
    if base_order is None or base_order == "":
        if base_required:
            raise ValueError(
                f"{kind.upper()} at {path} missing 'base_order' — a literal string "
                "path to the base OPORD YAML is required."
            )
        data, _ = _load_yaml_with_variables(path)
        return model.model_validate(data), None
    if not isinstance(base_order, str):
        raise ValueError(
            f"{kind.upper()} at {path} has invalid 'base_order' — must be a string path"
            + ("." if base_required else " or omitted.")
        )
    base_path = (path.parent / base_order).resolve()
    base, base_vars = load_opord_with_vars(base_path)
    extra: dict[str, Any] = {**base_vars, "base": base, "base_vars": base_vars}
    data, _ = _load_yaml_with_variables(path, extra_vars=extra)
    return model.model_validate(data), base


def load_frago(yaml_path: Path | str) -> tuple[FRAGO, OPORD]:
    """Load a FRAGO YAML and its referenced base OPORD. Returns (frago, base).

    The FRAGO YAML must have ``kind: frago`` at top level and a ``base_order``
    path (relative to the FRAGO file) pointing at the parent OPORD. The base
    is loaded first, then exposed in the FRAGO's variable-interpolation
    namespace under THREE keys:

    * ``base`` — the full base OPORD Pydantic model (attribute access:
      ``{{ base.header.dtg }}``, ``{{ base.mission }}``, etc.)
    * ``base_vars`` — the base's ``variables:`` dict, explicit namespace
      (``{{ base_vars.h_hour }}``)
    * every base variable merged flat (``{{ h_hour }}`` works directly;
      FRAGO-declared variables of the same name override)
    """
    frago, base = _load_document_with_base(Path(yaml_path), model=FRAGO)
    assert base is not None
    return frago, base


def _frago_effective_header(frago: FRAGO, base: OPORD) -> dict[str, Any]:
    """Merge the FRAGO header with fall-through to the base OPORD header.
    FRAGO values win when set; otherwise inherit from base. Keeps the
    FRAGO YAML DRY — authors only declare fields that actually differ."""
    bh = base.header
    return {
        "classification": frago.classification or bh.classification,
        "classification_caveat": frago.classification_caveat or bh.classification_caveat,
        "issuing_headquarters": frago.issuing_headquarters or bh.issuing_headquarters,
        "place_of_issue": frago.place_of_issue or bh.place_of_issue,
        "dtg": frago.dtg,  # always FRAGO's own issue DTG
        "time_zone": frago.time_zone or bh.time_zone,
        "copy_number": frago.copy_number if frago.copy_number is not None else bh.copy_number,
        "number_of_copies": (
            frago.number_of_copies if frago.number_of_copies is not None
            else bh.number_of_copies
        ),
        "author": frago.author or bh.author,
    }


def _frago_ctx(frago: FRAGO, base: OPORD) -> dict[str, Any]:
    """Template context for FRAGO rendering — carries both the delta and
    the base order, plus branding inherited from the base (page_icon,
    watermark, logo, operation name/number). `eff` is the FRAGO header
    with base-OPORD fallback applied, so the template reads a single
    effective-value source per field."""
    return {
        "frago": frago,
        "base": base,
        "eff": _frago_effective_header(frago, base),
        "generated_at": _now_utc_stamp(),
        "watermark_url": _resolve_watermark(base),
        "page_icon": base.header.page_icon,
        "logo": base.header.logo,
    }


def render_frago_html(
    frago: FRAGO,
    base: OPORD,
    *,
    context: dict[str, Any] | None = None,
) -> str:
    """Render a FRAGO as standalone HTML. Reuses the OPORD typed-body
    walker for any structured paragraph content and auto-emits 'No change'
    stubs for paragraphs the FRAGO leaves unset."""
    env = _make_env(html=True)
    template = env.get_template("frago.html.j2")
    return template.render(**(context or _frago_ctx(frago, base)))


def render_frago_markdown(
    frago: FRAGO,
    base: OPORD,
    *,
    context: dict[str, Any] | None = None,
) -> str:
    env = _make_env(html=False)
    template = env.get_template("frago.md.j2")
    return template.render(**(context or _frago_ctx(frago, base)))


def render_frago_pdf(
    frago: FRAGO,
    base: OPORD,
    out_path: Path | str,
    *,
    _html: str | None = None,
) -> Path:
    from weasyprint import HTML  # heavy import — deferred
    raw = _html if _html is not None else render_frago_html(frago, base)
    html = _inline_stylesheet(raw)
    out_path = Path(out_path)
    HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf(
        target=str(out_path), stylesheets=[_pdf_stylesheet()]
    )
    return out_path


def render_frago_all(
    frago: FRAGO,
    base: OPORD,
    out_dir: Path | str,
    stem: str,
    write_markdown: bool = True,
    write_html: bool = True,
    write_pdf: bool = True,
) -> dict[str, Path]:
    ctx = _frago_ctx(frago, base)
    return _render_document_all(
        out_dir, stem,
        render_md_fn=lambda: render_frago_markdown(frago, base, context=ctx),
        render_html_fn=lambda: render_frago_html(frago, base, context=ctx),
        render_pdf_fn=lambda out, html=None: render_frago_pdf(
            frago, base, out, _html=html,
        ),
        write_markdown=write_markdown,
        write_html=write_html,
        write_pdf=write_pdf,
    )


def load_warno(yaml_path: Path | str) -> tuple[WARNO, OPORD | None]:
    """Load a WARNO YAML and (optionally) its referenced base OPORD.

    Returns ``(warno, base)`` — ``base`` is ``None`` when the WARNO has no
    ``base_order`` (preliminary order issued before the higher-HQ OPORD
    exists). When ``base_order`` IS set, the base is loaded and exposed
    exactly like FRAGO: ``base`` / ``base_vars`` / flat vars in the
    interpolation namespace."""
    return _load_document_with_base(Path(yaml_path), model=WARNO)


def _warno_effective_header(warno: WARNO, base: OPORD | None) -> dict[str, Any]:
    """Effective header for a WARNO: own fields when standalone, or
    FRAGO-style fall-through to the base OPORD header when a base is set."""
    if base is None:
        return {
            "classification": warno.classification,
            "classification_caveat": warno.classification_caveat,
            "issuing_headquarters": warno.issuing_headquarters,
            "place_of_issue": warno.place_of_issue,
            "dtg": warno.dtg,
            "time_zone": warno.time_zone,
            "copy_number": warno.copy_number,
            "number_of_copies": warno.number_of_copies,
            "author": warno.author,
            "operation_name": warno.operation_name,
            "operation_order_number": warno.operation_order_number,
        }
    bh = base.header
    return {
        "classification": warno.classification or bh.classification,
        "classification_caveat": warno.classification_caveat or bh.classification_caveat,
        "issuing_headquarters": warno.issuing_headquarters or bh.issuing_headquarters,
        "place_of_issue": warno.place_of_issue or bh.place_of_issue,
        "dtg": warno.dtg,  # always WARNO's own issue DTG
        "time_zone": warno.time_zone or bh.time_zone,
        "copy_number": warno.copy_number if warno.copy_number is not None else bh.copy_number,
        "number_of_copies": (
            warno.number_of_copies if warno.number_of_copies is not None
            else bh.number_of_copies
        ),
        "author": warno.author or bh.author,
        "operation_name": warno.operation_name or bh.operation_name,
        "operation_order_number": warno.operation_order_number or bh.operation_order_number,
    }


def _warno_ctx(warno: WARNO, base: OPORD | None) -> dict[str, Any]:
    """Template context for WARNO rendering. Branding (watermark, page_icon,
    logo) prefers WARNO-declared values and falls through to the base header
    when a base is set; standalone WARNOs use only their own branding."""
    if base is None:
        watermark_url = _watermark_from_value(warno.watermark)
        page_icon = warno.page_icon
        logo = warno.logo
    else:
        bh = base.header
        watermark_url = _watermark_from_value(warno.watermark or bh.watermark)
        page_icon = warno.page_icon or bh.page_icon
        logo = warno.logo or bh.logo
    return {
        "warno": warno,
        "base": base,
        "eff": _warno_effective_header(warno, base),
        "generated_at": _now_utc_stamp(),
        "watermark_url": watermark_url,
        "page_icon": page_icon,
        "logo": logo,
    }


def render_warno_html(
    warno: WARNO,
    base: OPORD | None,
    *,
    context: dict[str, Any] | None = None,
) -> str:
    """Render a WARNO as standalone HTML. Unset paragraphs render as 'To be
    published' stubs; sections the WARNO did populate render normally."""
    env = _make_env(html=True)
    template = env.get_template("warno.html.j2")
    return template.render(**(context or _warno_ctx(warno, base)))


def render_warno_markdown(
    warno: WARNO,
    base: OPORD | None,
    *,
    context: dict[str, Any] | None = None,
) -> str:
    env = _make_env(html=False)
    template = env.get_template("warno.md.j2")
    return template.render(**(context or _warno_ctx(warno, base)))


def render_warno_pdf(
    warno: WARNO,
    base: OPORD | None,
    out_path: Path | str,
    *,
    _html: str | None = None,
) -> Path:
    from weasyprint import HTML  # heavy import — deferred
    raw = _html if _html is not None else render_warno_html(warno, base)
    html = _inline_stylesheet(raw)
    out_path = Path(out_path)
    HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf(
        target=str(out_path), stylesheets=[_pdf_stylesheet()]
    )
    return out_path


def render_warno_all(
    warno: WARNO,
    base: OPORD | None,
    out_dir: Path | str,
    stem: str,
    write_markdown: bool = True,
    write_html: bool = True,
    write_pdf: bool = True,
) -> dict[str, Path]:
    ctx = _warno_ctx(warno, base)
    return _render_document_all(
        out_dir, stem,
        render_md_fn=lambda: render_warno_markdown(warno, base, context=ctx),
        render_html_fn=lambda: render_warno_html(warno, base, context=ctx),
        render_pdf_fn=lambda out, html=None: render_warno_pdf(
            warno, base, out, _html=html,
        ),
        write_markdown=write_markdown,
        write_html=write_html,
        write_pdf=write_pdf,
    )


def _render_document_all(
    out_dir: Path | str,
    stem: str,
    *,
    render_md_fn: Callable[[], str],
    render_html_fn: Callable[[], str],
    render_pdf_fn: Callable[..., Path],
    write_markdown: bool,
    write_html: bool,
    write_pdf: bool,
) -> dict[str, Path]:
    """Shared driver for render_*_all: build each requested format exactly
    once, passing the already-rendered HTML through to the PDF step so the
    template engine runs at most once per format."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}
    if write_markdown:
        md_path = out_dir / f"{stem}.md"
        md_path.write_text(render_md_fn(), encoding="utf-8")
        outputs["markdown"] = md_path
    if write_html or write_pdf:
        raw_html = render_html_fn()
        if write_html:
            html_path = out_dir / f"{stem}.html"
            html_path.write_text(_inline_stylesheet(raw_html), encoding="utf-8")
            outputs["html"] = html_path
        if write_pdf:
            pdf_path = out_dir / f"{stem}.pdf"
            render_pdf_fn(pdf_path, html=raw_html)
            outputs["pdf"] = pdf_path
    return outputs


def _now_utc_stamp() -> str:
    """UTC stamp in doctrinal DTG-adjacent form, e.g. '191830ZAPR26'."""
    return datetime.now(timezone.utc).strftime("%d%H%MZ%b%y").upper()


def _render_ctx(opord: OPORD) -> dict[str, Any]:
    return {
        "opord": opord,
        "annex_directory": opord.annex_directory(),
        "generated_at": _now_utc_stamp(),
    }


def render_markdown(opord: OPORD, context: dict[str, Any] | None = None) -> str:
    env = _make_env(html=False)
    template = env.get_template("opord.md.j2")
    return template.render(**(context or _render_ctx(opord)))


def render_html(opord: OPORD, context: dict[str, Any] | None = None) -> str:
    """Raw template output — references styles.css as an external stylesheet.

    Used as WeasyPrint input. For a portable browser-viewable file, use
    :func:`render_html_standalone`.
    """
    env = _make_env(html=True)
    template = env.get_template("opord.html.j2")
    ctx = dict(context) if context else _render_ctx(opord)
    if "watermark_url" not in ctx:
        ctx["watermark_url"] = _resolve_watermark(opord)
    return template.render(**ctx)


def _inline_stylesheet(html: str) -> str:
    css_block = f"<style>\n{_stylesheet_text()}\n</style>"
    if "</head>" in html:
        return html.replace("</head>", f"{css_block}\n</head>", 1)
    return html.replace("<body", f"{css_block}\n<body", 1)


def render_html_standalone(opord: OPORD) -> str:
    """Self-contained HTML with the stylesheet inlined — ready to open in a browser."""
    return _inline_stylesheet(render_html(opord))


@lru_cache(maxsize=1)
def _pdf_stylesheet() -> "_WeasyCSS":
    """Cache the parsed stylesheet so WeasyPrint doesn't re-parse per render."""
    from weasyprint import CSS  # heavy import — deferred
    return CSS(string=_stylesheet_text())


def render_pdf(opord: OPORD, out_path: Path | str, _html: str | None = None) -> Path:
    from weasyprint import HTML  # heavy import — deferred

    html = _html if _html is not None else render_html(opord)
    out_path = Path(out_path)
    HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf(
        target=str(out_path),
        stylesheets=[_pdf_stylesheet()],
    )
    return out_path


# ---------------------------------------------------------------------------
# Standalone product exports — pull ANY list-of-models artifact out of the
# OPORD and render it as a self-contained PDF/HTML/CSV suitable for slide
# paste or distribution separate from the full order.
#
# Two addressing modes:
#   * Short alias (jpitl, pir, cap_tracks, …) — entry in _PRODUCT_ALIASES
#   * Dotted path — 'annex.D.jpitl', 'execution.tasks_to_subordinate_units',
#     'situation.area_of_operations.weather.forecast_by_period'. The leading
#     token 'annex.<LETTER>' hops into that annex's typed_body.
#
# Run `opord list-products <input>.yaml` to discover what's available in
# a particular OPORD (which typed lists have content).
# ---------------------------------------------------------------------------
_PRODUCT_ALIASES: dict[str, tuple[str, str, str]] = {
    # (path, title, subtitle)
    "jpitl":             ("annex.D.jpitl",                                 "Joint Prioritized Integrated Target List",      "JP 3-60 / ATP 3-60"),
    "tst":               ("annex.D.time_sensitive_targets",                "Time-Sensitive Target List",                    "JP 3-60 / ATP 3-60"),
    "hptl":              ("annex.D.high_payoff_target_list",               "High-Payoff Target List",                       "ATP 3-60"),
    "fscm":              ("annex.D.fire_support_coordination_measures",    "Fire Support Coordination Measures",            "ATP 3-09"),
    "agm":               ("annex.D.attack_guidance_matrix",                "Attack Guidance Matrix",                        "ATP 3-60"),
    "cas_9line":         ("annex.D.cas_nine_lines",                        "9-Line CAS Briefs",                             "JP 3-09.3 / AFTTP 3-2.6"),
    "cas_requests":      ("annex.D.close_air_support_requests",            "Close Air Support Requests",                    "ATP 3-09.32"),
    "priority_of_fires": ("annex.D.priority_of_fires_by_phase",            "Priority of Fires by Phase",                    "ATP 3-09"),
    "pir":               ("annex.B.priority_intelligence_requirements",    "Priority Intelligence Requirements",            "ADP 2-0"),
    "hvtl":              ("annex.B.high_value_target_list",                "High-Value Target List",                        "ATP 3-60"),
    "enemy_coas":        ("annex.B.enemy_courses_of_action",               "Enemy Courses of Action",                       "ATP 2-01.3"),
    "phases":            ("annex.C.phases",                                "Operation Phases",                              "ADP 5-0"),
    "decision_points":   ("annex.C.decision_points",                       "Decision Support Matrix",                       "ADP 5-0"),
    "control_measures":  ("annex.C.control_measures",                      "Maneuver Control Measures",                     "FM 1-02.2"),
    "cap_tracks":        ("annex.C.airspace_control.cap_tracks",           "Combat Air Patrol Tracks",                      "ATP 3-52"),
    "aar_tracks":        ("annex.C.airspace_control.aar_tracks",           "Air-to-Air Refueling Tracks",                   "JP 3-17"),
    "awacs_orbits":      ("annex.C.airspace_control.awacs_orbits",         "AWACS / Airborne C2 Orbits",                    "ATP 3-52"),
    "aic_sectors":       ("annex.C.airspace_control.aic_sectors",          "Air Intercept Controller Sectors",              "ATP 3-52"),
    "airspace_zones":    ("annex.C.airspace_control.airspace_zones",       "Airspace Zones (ROZ / HIDACZ / WEZ / NFZ)",     "JP 3-52"),
    "geo_refs":          ("annex.C.airspace_control.geo_refs",             "Geographic Reference Points",                   "ATP 3-52"),
    "mrr":               ("annex.C.airspace_control.ingress_corridors",    "Minimum-Risk Routes / Ingress Corridors",       "JP 3-52"),
    "task_org":          ("annex.A.task_organization_list",                "Task Organization",                             "FM 6-0 App D"),
    "cross_attachments": ("annex.A.cross_attachments",                     "Cross-Attachments and Detachments",             "FM 6-0"),
    "pace_plans":        ("annex.H.pace_plans",                            "PACE Plans",                                    "FM 6-02"),
    "comsec":            ("annex.H.comsec_schedule",                       "COMSEC Schedule",                               "FM 6-02"),
    "retrans":           ("annex.H.retrans_sites",                         "Retrans Sites",                                 "FM 6-02"),
    "subordinate_tasks": ("execution.tasks_to_subordinate_units",          "Tasks to Subordinate Units",                    "FM 6-0 Para 3"),
    "wx_forecast":       ("situation.area_of_operations.weather.forecast_by_period", "Weather Forecast by Period",           "ATP 2-22.5"),
}


def _walk_path(opord: OPORD, path: str) -> Any:
    """Resolve a dotted path through the OPORD. Supports 'annex.<LETTER>.<...>'
    as shorthand for 'opord.annexes[where letter=X].typed_body.<...>'."""
    parts = path.split(".")
    if not parts:
        raise ValueError("empty product path")
    if parts[0].lower() == "annex" and len(parts) >= 2:
        letter = parts[1].upper()
        annex = next((a for a in opord.annexes if a.letter == letter), None)
        if annex is None:
            raise ValueError(f"Annex {letter!r} not found in this OPORD")
        if annex.typed_body is None:
            raise ValueError(f"Annex {letter!r} has no typed_body; nothing to export at {path!r}")
        node: Any = annex.typed_body
        rest = parts[2:]
    else:
        node = opord
        rest = parts
    for segment in rest:
        if segment.isdigit() and isinstance(node, list):
            node = node[int(segment)]
        elif hasattr(node, segment):
            node = getattr(node, segment)
        else:
            raise ValueError(
                f"Cannot descend segment {segment!r} of path {path!r} "
                f"on {type(node).__name__}"
            )
    return node


def _resolve_product(opord: OPORD, product: str) -> tuple[list, str, str, str]:
    """Return (entries, title, subtitle, resolved_path) for the named product.
    ``product`` is either a short alias in ``_PRODUCT_ALIASES`` or a dotted path."""
    if product in _PRODUCT_ALIASES:
        path, title, subtitle = _PRODUCT_ALIASES[product]
    else:
        path = product
        title = _humanize(path.rsplit(".", 1)[-1])
        subtitle = f"Path: {path}"
    entries = _walk_path(opord, path)
    if not isinstance(entries, list):
        raise ValueError(
            f"{product!r} resolves to {type(entries).__name__} at {path!r}; "
            "export only supports lists of structured entries."
        )
    if entries and not isinstance(entries[0], BaseModel):
        raise ValueError(
            f"{product!r} resolves to a list of {type(entries[0]).__name__} "
            f"at {path!r}; export only supports lists of Pydantic models."
        )
    return entries, title, subtitle, path


def discover_products(opord: OPORD) -> list[tuple[str, int, str]]:
    """Walk the OPORD tree and return every list-of-BaseModel field as a list
    of (path, entry_count, model_name) tuples. Used by `opord list-products`."""
    results: list[tuple[str, int, str]] = []

    def walk(node: Any, path: str) -> None:
        if not isinstance(node, BaseModel):
            return
        for name in node.__class__.model_fields:
            value = getattr(node, name, None)
            if not has_content(value):
                continue
            child_path = f"{path}.{name}" if path else name
            if isinstance(value, list) and value and isinstance(value[0], BaseModel):
                results.append((child_path, len(value), value[0].__class__.__name__))
            elif isinstance(value, BaseModel):
                walk(value, child_path)

    walk(opord.header, "header")
    walk(opord.situation, "situation")
    walk(opord.execution, "execution")
    walk(opord.sustainment, "sustainment")
    walk(opord.command_and_signal, "command_and_signal")
    walk(opord.authentication, "authentication")
    for annex in opord.annexes:
        if annex.typed_body is not None:
            walk(annex.typed_body, f"annex.{annex.letter}")
    return results


def render_product_html(opord: OPORD, product: str) -> str:
    """Render a single list product as a standalone HTML document with the
    OPORD header for branding. Uses the main typed-body renderer so any
    configured split-render/detail-card layout applies automatically."""
    entries, title, subtitle, _path = _resolve_product(opord, product)
    env = _make_env(html=True)
    template = env.get_template("product.html.j2")
    ctx = _render_ctx(opord)
    ctx.setdefault("watermark_url", _resolve_watermark(opord))
    ctx["product_title"] = title
    ctx["product_subtitle"] = subtitle
    ctx["product_body_html"] = _render_list_of_models_html(title, entries) if entries else ""
    return template.render(**ctx)


def render_product_pdf(opord: OPORD, out_path: Path | str, product: str) -> Path:
    from weasyprint import HTML  # heavy import — deferred

    html = _inline_stylesheet(render_product_html(opord, product))
    out_path = Path(out_path)
    HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf(
        target=str(out_path), stylesheets=[_pdf_stylesheet()]
    )
    return out_path


def render_product_csv(opord: OPORD, product: str) -> str:
    """Flatten every entry of the named product to CSV for spreadsheet paste."""
    import csv
    from io import StringIO

    entries, _title, _subtitle, _path = _resolve_product(opord, product)
    if not entries:
        return ""
    cls = entries[0].__class__
    fieldnames = list(cls.model_fields.keys())
    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()
    for entry in entries:
        row: dict[str, str] = {}
        for name in fieldnames:
            v = getattr(entry, name, None)
            if v is None:
                row[name] = ""
            elif isinstance(v, list):
                row[name] = "; ".join(str(x) for x in v)
            elif isinstance(v, BaseModel):
                row[name] = v.model_dump_json()
            else:
                row[name] = str(v)
        writer.writerow(row)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Kneeboard card rendering — 768×1024 PNG for DCS World
# ---------------------------------------------------------------------------

def render_kneeboard_html(card, card_index: int = 0) -> str:
    """Render a single KneeboardCard as self-contained HTML sized for 768×1024."""
    env = _make_env(html=True)
    template = env.get_template("kneeboard.html.j2")
    return template.render(
        card=card,
        card_index=card_index,
        generated_at=_now_utc_stamp(),
    )


def render_kneeboard_png(card, out_path: Path | str, card_index: int = 0) -> Path:
    """Render a single KneeboardCard to a 768×1024 PNG.

    Renders HTML → PDF via WeasyPrint, then converts the single-page PDF to
    PNG via ``pdftoppm`` (poppler-utils).  Falls back to keeping the PDF if
    poppler is not installed."""
    import shutil
    import subprocess
    import tempfile

    from weasyprint import HTML

    html = render_kneeboard_html(card, card_index=card_index)
    out_path = Path(out_path)

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "card.pdf"
        HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf(target=str(pdf_path))

        if shutil.which("pdftoppm"):
            prefix = Path(tmp) / "card"
            subprocess.run(
                [
                    "pdftoppm", "-png", "-r", "96",
                    "-singlefile", str(pdf_path), str(prefix),
                ],
                check=True,
                capture_output=True,
            )
            png_tmp = prefix.with_suffix(".png")
            shutil.move(str(png_tmp), str(out_path))
        else:
            fallback = out_path.with_suffix(".pdf")
            shutil.move(str(pdf_path), str(fallback))
            warnings.warn(
                f"pdftoppm not found — wrote PDF instead: {fallback}. "
                "Install poppler-utils for PNG output.",
                stacklevel=2,
            )
            return fallback

    return out_path


def render_kneeboards(
    doc,
    out_dir: Path | str,
    stem: str,
) -> list[Path]:
    """Render all kneeboard cards from an OPORD or FRAGO to numbered PNGs.

    Output files are named ``<stem>_kneeboard_001.png``, etc. — DCS World
    sorts kneeboard pages alphanumerically so zero-padded numbers maintain
    the correct order."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, card in enumerate(doc.kneeboards):
        filename = f"{stem}_kneeboard_{i + 1:03d}.png"
        p = render_kneeboard_png(card, out_dir / filename, card_index=i)
        paths.append(p)
    return paths


def render_all(
    opord: OPORD,
    out_dir: Path | str,
    stem: str,
    write_markdown: bool = True,
    write_html: bool = True,
    write_pdf: bool = True,
) -> dict[str, Path]:
    ctx = _render_ctx(opord)
    return _render_document_all(
        out_dir, stem,
        render_md_fn=lambda: render_markdown(opord, context=ctx),
        render_html_fn=lambda: render_html(opord, context=ctx),
        render_pdf_fn=lambda out, html=None: render_pdf(opord, out, _html=html),
        write_markdown=write_markdown,
        write_html=write_html,
        write_pdf=write_pdf,
    )
