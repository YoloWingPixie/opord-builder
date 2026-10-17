"""Render an order (OPORD, FRAGO, WARNO) as Markdown, HTML and PDF, and export its lists as products."""

from __future__ import annotations

import base64
import csv
import urllib.error
import urllib.request
import warnings
from datetime import datetime, timezone
from functools import cache, lru_cache
from html import escape
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

from jinja2 import (
    ChainableUndefined,
    Environment,
    FileSystemLoader,
    pass_context,
    select_autoescape,
)

from opord_builder import generic, themes
from opord_builder._paths import STYLESHEET, TEMPLATES_DIR
from opord_builder.format import dtg, fmt, has_content, humanize, letter_for, paragraphs
from opord_builder.generic import Walk, child
from opord_builder.load import ORDER, PRINT, at, ext_schema, schema_index
from opord_builder.order import Order

OPORD_SCHEMA = "urn:openaix:schema:opord:0.2.0-draft.1"
CANONICAL_ANNEXES = {
    "A": "Task Organization", "B": "Intelligence", "C": "Operations", "D": "Fires", "E": "Protection",
    "F": "Sustainment", "G": "Engineer", "H": "Signal", "I": "Not Used", "J": "Public Affairs",
    "K": "Civil Affairs Operations", "L": "Information Collection", "M": "Assessment", "N": "Space Operations",
    "O": "Not Used", "P": "Host-Nation Support", "Q": "Knowledge Management", "R": "Reports",
    "S": "Special Technical Operations", "T": "Not Used", "U": "Inspector General",
    "V": "Interagency Coordination", "W": "Not Used", "X": "Not Used", "Y": "Not Used", "Z": "Distribution",
}  # fmt: skip
RESERVED_LETTERS = set("IOTWXY")
RELATIONSHIPS = {
    "operational_control": "OPCON", "tactical_control": "TACON", "administrative_control": "ADCON",
    "direct_support": "DS", "general_support": "GS", "reinforcing": "R", "general_support_reinforcing": "GSR",
}  # fmt: skip
PARAGRAPHS = (("situation", "Situation"), ("mission", "Mission"), ("execution", "Execution"),
              ("sustainment", "Sustainment"), ("command_and_signal", "Command and Signal"))  # fmt: skip
_IMG_SUFFIXES = (".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif")

_WATERMARK_ACCENT = "#0b3d91"
_WATERMARK_ALPHA = 0.10
_WATERMARK_MAX_DIM = 1200  # px — cap source before embedding to keep HTML small
_WATERMARK_FETCH_TIMEOUT = 5  # s
_WATERMARK_MAX_BYTES = 2 * 1024 * 1024  # 2 MiB cap on fetched image bytes


def is_image_watermark(value: str) -> bool:
    v = value.lower()
    return v.startswith(("http://", "https://")) or v.endswith(_IMG_SUFFIXES)


@lru_cache(maxsize=2)
def fade_image(source: str) -> str:
    """Download + alpha-fade + base64 once per render (same watermark reused
    on every page). Separated from the SVG path so PIL is only imported when
    an image watermark is actually used."""
    from PIL import Image

    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=_WATERMARK_FETCH_TIMEOUT) as resp:
            img_bytes = resp.read(_WATERMARK_MAX_BYTES + 1)
            if len(img_bytes) > _WATERMARK_MAX_BYTES:
                raise ValueError(
                    f"watermark image exceeds {_WATERMARK_MAX_BYTES} bytes"
                )
    else:
        img_bytes = Path(source).read_bytes()

    img = Image.open(BytesIO(img_bytes)).convert("RGBA")
    img.thumbnail((_WATERMARK_MAX_DIM, _WATERMARK_MAX_DIM))
    lut = [int(i * _WATERMARK_ALPHA) for i in range(256)]
    img.putalpha(img.split()[3].point(lut))
    out = BytesIO()
    img.save(out, "PNG", optimize=True)
    return f"data:image/png;base64,{base64.b64encode(out.getvalue()).decode('ascii')}"


def text_watermark_svg(text: str) -> str:
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


def watermark_from_value(wm: str | None) -> str:
    if not wm:
        return ""
    if is_image_watermark(wm):
        try:
            return fade_image(wm)
        except (OSError, urllib.error.URLError, ValueError, ImportError) as exc:
            warnings.warn(
                f"watermark fade failed ({exc!r}); embedding raw URL", stacklevel=2
            )
            return wm
    return text_watermark_svg(wm)


# --------------------------------------------------------------------------- environment


def zone(value: str | None) -> str:
    return "ZULU" if value == "Z" else value or ""


def stamp() -> str:
    """UTC stamp in DTG-like form, e.g. `191830ZAPR26`."""
    return datetime.now(timezone.utc).strftime("%d%H%MZ%b%y").upper()


@cache
def env(html: bool) -> Environment:
    e = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "htm"]) if html else False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=ChainableUndefined,
        auto_reload=False,
    )
    e.globals.update(
        has_content=has_content,
        letter_for=letter_for,
        section=section,
        annex_view=annex_view,
        directory=directory,
    )
    e.filters.update(dtg=dtg, fmt=fmt, zone=zone, paragraphs=paragraphs)
    return e


def root(schema_id: str) -> tuple[dict, dict]:
    s = schema_index()[schema_id]
    return s, s


def ext_root() -> tuple[dict, dict]:
    s = ext_schema("order")
    return s, s


@pass_context
def section(ctx, key: str, num: str, skip: tuple = ()) -> str:
    """The generic body of a paragraph: its typed content and its extension, walked together."""
    o: Order = ctx["o"]
    ext = ext_root()
    srcs = [
        (o.doc.get(key), child(root(OPORD_SCHEMA), key)),
        (o.x.get(key), child(ext, key)),
    ]
    return generic.render(Walk(o.res, ctx["html"]), key, srcs, num, frozenset(skip))


def directory(o: Order) -> list[dict]:
    """All 26 annex letters with title and status; the extension's status wins, else content decides."""
    ext = o.x.get("annexes") or {}
    out = []
    for letter, title in CANONICAL_ANNEXES.items():
        a = ext.get(letter) or {}
        has = letter in (o.doc.get("annexes") or {}) or has_content(
            {k: v for k, v in a.items() if k != "status"}
        )
        status = a.get("status") or (
            "published"
            if has
            else "not_used"
            if letter in RESERVED_LETTERS
            else "omitted"
        )
        out.append(
            {"letter": letter, "title": a.get("title") or title, "status": status}
        )
    return out


def annex_blocks(w: Walk, o: Order, letter: str) -> tuple[list, list]:
    """(content blocks, appendix blocks) of one annex: typed document content joined with the extension."""
    typed = {
        k: v
        for k, v in ((o.doc.get("annexes") or {}).get(letter) or {}).items()
        if k != "summary"
    }
    ext = (o.x.get("annexes") or {}).get(letter) or {}
    doc_sch = child(child(root(OPORD_SCHEMA), "annexes"), letter)
    ext_sch = child(child(ext_root(), "annexes"), letter)
    srcs = [(typed, doc_sch), (ext.get("typed_body"), child(ext_sch, "typed_body"))]
    body = generic.blocks(w, "annex", f"annex.{letter}", srcs)
    content = body[0][2] if body else []
    groups = ext.get("call_sign_groups") or []
    if groups:
        content.append(("sec", "Call Sign Assignments", [
            blk for g in groups for blk in generic.listing(w, g.get("category") or "Call signs", "", [(g["entries"], None)])
        ]))  # fmt: skip
    if ext.get("distribution_list"):
        content.append(("list", "Distribution List", ext["distribution_list"]))
    appendices = []
    for ap in ext.get("appendices") or []:
        kids: list = [("text", None, ap["body"])] if ap.get("body") else []
        for ft in ap.get("frequency_tables") or []:
            rows = [channel_row(r, o.res) for r in ft.get("channels") or []]
            title = " · ".join(t for t in (ft.get("title"), ft.get("sub_title")) if t)
            kids += generic.listing(w, title or "Frequencies", "", [(rows, None)])
        if ap.get("distribution_list"):
            kids.append(("list", "Distribution List", ap["distribution_list"]))
        appendices.append(
            ("sec", f"Appendix {ap['number']} ({letter}) — {ap['title']}", kids)
        )
    return content, appendices


def channel_row(row: dict, res: dict) -> dict:
    """A frequency-table row: the resources channel it names, with the row's own fields laid over it."""
    rec = res.get("channels", {}).get(row.get("channel_ref")) or {}
    base = {
        "name": rec.get("name"),
        "channel": None,
        "frequency": rec.get("frequency"),
        "purpose": rec.get("usage"),
    }
    return {
        **{k: v for k, v in base.items() if v},
        **{k: v for k, v in row.items() if k != "channel_ref"},
    }


@pass_context
def annex_view(ctx, letter: str) -> dict:
    """{intro, content, appendices}: one annex printed as Markdown or HTML."""
    o: Order = ctx["o"]
    w = Walk(o.res, ctx["html"])
    emit = generic.html if w.html else generic.md
    content, appendices = annex_blocks(w, o, letter)
    ext = (o.x.get("annexes") or {}).get(letter) or {}
    intro = (
        ((o.doc.get("annexes") or {}).get(letter) or {}).get("summary")
        or ext.get("body")
        or ""
    )
    return {
        "intro": intro,
        "content": emit(content, 1, "", True),
        "appendices": emit(appendices, 1, ""),
    }


def effective(o: Order) -> dict[str, Any]:
    """The header values to print: the document's own, falling back to the base order's."""
    h, b = o.head, o.base or {}

    def own(field: str) -> Any:
        return h.get(field) or b.get(field)

    def meta(field: str) -> Any:
        return (h.get("meta") or {}).get(field) or (b.get("meta") or {}).get(field)

    pr = {**((b.get("extensions") or {}).get(PRINT) or {}), **o.print}
    return {
        "classification": meta("classification") or "UNCLASSIFIED",
        "caveat": pr.get("classification_caveat"),
        "hq": own("issuing_headquarters") or "", "place": pr.get("place_of_issue") or "", "tz": zone(own("time_zone")),
        "dtg": dtg(h["date_time"]) if h.get("date_time") else "", "author": meta("author") or "",
        "op_name": own("operation_name") or "", "op_number": own("order_number") or "",
        "base_dtg": dtg(b["date_time"]) if b.get("date_time") else "", "print": pr,
        "number": h.get("frago_number") or (o.x.get("warno_number") if o.kind == "warno" else ""),
        "previous": (h.get("extensions", {}).get(ORDER) or {}).get("previous_fragos" if o.kind == "frago" else "previous_warnos") or [],
        "auth": h.get("authentication") or b.get("authentication") or {},
        "ack": ((h.get("acknowledgement") or b.get("acknowledgement") or {}).get("acknowledge")),
        "distribution": ((h.get("extensions", {}).get(ORDER) or {}).get("authentication") or o.x.get("authentication") or {}).get("distribution"),
    }  # fmt: skip


def context(o: Order, html: bool, theme: str | None = None) -> dict[str, Any]:
    units = o.doc.get("task_organization") or {}
    kids: dict[str | None, list[str]] = {}
    for uid, u in units.items():
        kids.setdefault(u.get("parent"), []).append(uid)
    rels = {
        r["unit"]: r["relationship"]
        for r in ((o.doc.get("annexes") or {}).get("A") or {}).get("relationships", [])
    }
    return {
        "o": o, "doc": o.doc, "head": o.head, "x": o.x, "res": o.res, "html": html, "eff": (eff := effective(o)),
        "print": eff["print"],
        "paragraphs_list": PARAGRAPHS, "annex_letters": [l for l in CANONICAL_ANNEXES if o.shown is None or f"annex:{l}" in o.shown], "units": units, "kids": kids, "rels": rels,
        "unit_ext": (o.x.get("header") or {}).get("units") or {},
        "generated_at": stamp(), "watermark_url": watermark_from_value(o.print.get("watermark")),
        "nonce": None, "theme": theme,
    }  # fmt: skip


# --------------------------------------------------------------------------- output


@cache
def stylesheet_text() -> str:
    return STYLESHEET.read_text(encoding="utf-8")


def render_markdown(o: Order) -> str:
    return env(False).get_template("order.md.j2").render(**context(o, False))


def theme_style(theme: str | None) -> str:
    """The `<style>` of a theme, layered after the base stylesheet; empty for the default look."""
    return f"\n<style>\n{themes.css(theme)}\n</style>" if theme else ""


def render_html(o: Order, theme: str | None = None) -> str:
    """HTML with the stylesheet inlined: ready for a browser, and the input to WeasyPrint.
    `theme` (else the document's own `theme`) names a file in templates/themes/."""
    theme = themes.resolve(theme, o.theme)
    css = f"<style>\n{stylesheet_text()}\n</style>{theme_style(theme)}"
    return (
        env(True)
        .get_template("order.html.j2")
        .render(**context(o, True, theme))
        .replace("</head>", f"{css}\n</head>", 1)
    )


@cache
def pdf_stylesheet(theme: str | None = None):
    """The base stylesheet, then the theme's: WeasyPrint applies it after the page's own, so it must carry both."""
    from weasyprint import CSS  # heavy import: deferred

    text = stylesheet_text() + (f"\n{themes.css(theme)}" if theme else "")
    return CSS(string=text)


def write_pdf(html_text: str, out: Path | str, theme: str | None = None) -> Path:
    from weasyprint import HTML

    HTML(string=html_text, base_url=str(TEMPLATES_DIR)).write_pdf(
        target=str(out), stylesheets=[pdf_stylesheet(theme)]
    )
    return Path(out)


def render_all(
    o: Order,
    out_dir: Path | str,
    stem: str,
    markdown: bool = True,
    html: bool = True,
    pdf: bool = True,
    theme: str | None = None,
) -> dict[str, Path]:
    """Write the requested formats. The HTML is built once and reused for the PDF."""
    theme = themes.resolve(theme, o.theme)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    if markdown:
        out["markdown"] = out_dir / f"{stem}.md"
        out["markdown"].write_text(render_markdown(o), encoding="utf-8")
    if html or pdf:
        text = render_html(o, theme)
        if html:
            out["html"] = out_dir / f"{stem}.html"
            out["html"].write_text(text, encoding="utf-8")
        if pdf:
            out["pdf"] = write_pdf(text, out_dir / f"{stem}.pdf", theme)
    return out


# --------------------------------------------------------------------------- products

X = f"/extensions/{ORDER}"
D, C, B = (
    f"{X}/annexes/D/typed_body",
    f"{X}/annexes/C/typed_body",
    f"{X}/annexes/B/typed_body",
)
# alias -> (typed pointer, extension pointer, title, subtitle); the two are joined by item identifier
ALIASES: dict[str, tuple[str | None, str | None, str, str]] = {
    "jpitl": (None, f"{D}/jpitl", "Joint Prioritized Integrated Target List", "JP 3-60 / ATP 3-60"),
    "tst": ("/annexes/D/targeting/time_sensitive_targets", f"{D}/time_sensitive_targets", "Time-Sensitive Target List", "JP 3-60 / ATP 3-60"),
    "hptl": ("/annexes/D/targeting/high_payoff_targets", f"{D}/high_payoff_target_list", "High-Payoff Target List", "ATP 3-60"),
    "fscm": ("/annexes/D/fire_support_coordination_measures", f"{D}/fire_support_coordination_measures", "Fire Support Coordination Measures", "ATP 3-09"),
    "agm": ("/annexes/D/targeting/high_payoff_targets", f"{D}/attack_guidance_matrix", "Attack Guidance Matrix", "ATP 3-60"),
    "cas_9line": ("/annexes/D/air_support/cas_briefs", f"{D}/cas_nine_lines", "9-Line CAS Briefs", "JP 3-09.3 / AFTTP 3-2.6"),
    "cas_requests": (None, f"{D}/close_air_support_requests", "Close Air Support Requests", "ATP 3-09.32"),
    "priority_of_fires": (None, f"{D}/priority_of_fires_by_phase", "Priority of Fires by Phase", "ATP 3-09"),
    "pir": (None, f"{B}/priority_intelligence_requirements", "Priority Intelligence Requirements", "ADP 2-0"),
    "hvtl": (None, f"{B}/high_value_target_list", "High-Value Target List", "ATP 3-60"),
    "enemy_coas": (None, f"{B}/enemy_courses_of_action", "Enemy Courses of Action", "ATP 2-01.3"),
    "phases": (None, f"{C}/phases", "Operation Phases", "ADP 5-0"),
    "decision_points": (None, f"{C}/decision_points", "Decision Support Matrix", "ADP 5-0"),
    "control_measures": ("/annexes/C/operation_overlay", f"{C}/control_measures", "Maneuver Control Measures", "FM 1-02.2"),
    "cap_tracks": (None, f"{C}/airspace_control/cap_tracks", "Combat Air Patrol Tracks", "ATP 3-52"),
    "aar_tracks": (None, f"{C}/airspace_control/aar_tracks", "Air-to-Air Refueling Tracks", "JP 3-17"),
    "awacs_orbits": (None, f"{C}/airspace_control/awacs_orbits", "AWACS / Airborne C2 Orbits", "ATP 3-52"),
    "aic_sectors": (None, f"{C}/airspace_control/aic_sectors", "Air Intercept Controller Sectors", "ATP 3-52"),
    "airspace_zones": (None, f"{C}/airspace_control/airspace_zones", "Airspace Zones (ROZ / HIDACZ / WEZ / NFZ)", "JP 3-52"),
    "geo_refs": (None, f"{C}/airspace_control/geo_refs", "Geographic Reference Points", "ATP 3-52"),
    "mrr": (None, f"{C}/airspace_control/ingress_corridors", "Minimum-Risk Routes / Ingress Corridors", "JP 3-52"),
    "task_org": ("/task_organization", None, "Task Organization", "FM 6-0 App D"),
    "cross_attachments": (None, f"{X}/annexes/A/typed_body/cross_attachments", "Cross-Attachments and Detachments", "FM 6-0"),
    "pace_plans": (None, f"{X}/annexes/H/typed_body/pace_plans", "PACE Plans", "FM 6-02"),
    "retrans": (None, f"{X}/annexes/H/typed_body/retrans_sites", "Retrans Sites", "FM 6-02"),
    "subordinate_tasks": ("/execution/tasks_to_subordinate_units", f"{X}/execution/tasks_to_subordinate_units", "Tasks to Subordinate Units", "FM 6-0 Para 3"),
}  # fmt: skip


def product_rows(o: Order, product: str) -> tuple[str, str, list, tuple | None]:
    """(title, subtitle, rows, row schema) of a product: an alias, or a JSON Pointer into the order document."""
    typed_p, ext_p, title, subtitle = ALIASES.get(product) or (
        product,
        None,
        humanize(product.rsplit("/", 1)[-1]),
        f"Pointer: {product}",
    )
    typed, ext = (
        at(o.doc, typed_p) if typed_p else None,
        at(o.doc, ext_p) if ext_p else None,
    )
    if isinstance(typed, dict):  # a map keyed by identifier
        typed = [{"id": k, **v} for k, v in typed.items()]
    if (
        typed is None
        and isinstance(ext, dict)
        and all(i in o.res.get("control_measures", {}) for i in ext)
    ):
        typed = list(ext)  # the measures the extension adds fields to
    srcs = [
        (v, s)
        for v, s in (
            (
                typed,
                MEASURES
                if isinstance(typed, list) and typed and isinstance(typed[0], str)
                else None,
            ),
            (ext, None),
        )
        if v
    ]
    if not srcs:
        return title, subtitle, [], None
    rows, sch = generic.rows_of(Walk(o.res), srcs)
    return title, subtitle, [r if isinstance(r, dict) else {"": r} for r in rows], sch


MEASURES = ({"type": "array", "items": {"x-catalog": "control_measures"}}, {})


def discover_products(o: Order) -> list[tuple[str, str, int]]:
    """(alias, pointer, entries) for each alias with rows, then every other array of objects in the document."""
    out = [
        (a, ALIASES[a][0] or ALIASES[a][1], len(rows))
        for a in ALIASES
        if (rows := product_rows(o, a)[2])
    ]
    known = {p for _, p, _ in out}

    def walk(node: Any, ptr: str) -> None:
        if (
            isinstance(node, list)
            and node
            and all(isinstance(i, dict) for i in node)
            and ptr not in known
        ):
            out.append(("", ptr, len(node)))
        for k, v in (
            node.items()
            if isinstance(node, dict)
            else enumerate(node)
            if isinstance(node, list)
            else ()
        ):
            walk(v, f"{ptr}/{str(k).replace('~', '~0').replace('/', '~1')}")

    walk(o.doc, "")
    return out


def render_product_html(o: Order, product: str, theme: str | None = None) -> str:
    theme = themes.resolve(theme, o.theme)
    title, subtitle, rows, sch = product_rows(o, product)
    body = (
        generic.html(
            generic.listing(Walk(o.res, True), title, "", [(rows, sch)]), 1, ""
        )
        if rows
        else ""
    )
    ctx = {
        **context(o, True, theme),
        "product_title": title,
        "product_subtitle": subtitle,
        "product_body_html": body,
    }
    css = f"<style>\n{stylesheet_text()}\n</style>{theme_style(theme)}"
    return (
        env(True)
        .get_template("product.html.j2")
        .render(**ctx)
        .replace("</head>", f"{css}\n</head>", 1)
    )


def render_product_csv(o: Order, product: str) -> str:
    _, _, rows, sch = product_rows(o, product)
    if not rows:
        return ""
    cols, body = generic.matrix(Walk(o.res), rows, sch)
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(cols)
    writer.writerows(body)
    return buf.getvalue()
