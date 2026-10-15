"""Render order content generically.

An order keeps its typed data in the OpenAIX document and the rest in the `org.opord-builder.order` extension. Both
are walked side by side, at the same path, in the order of the schemas' properties (or a hint where the reading
order differs). Labels come from the property names. The walk yields blocks that two small emitters print as
Markdown or HTML. No intermediate model is built.

Blocks:
  ("sec", label, [blocks])            a titled group
  ("text", label, str)                a labelled text
  ("kv", label, str)                  a short value
  ("list", label, [str])              bullets
  ("table", label, [head], [[cell]])  a table
  ("cards", [(title, [(key, value)])])  per-row details of a wide table
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

from opord_builder.format import (
    FORECAST_HEAD,
    dtg,
    fmt,
    forecast_row,
    has_content,
    humanize,
    letter_for,
    paragraphs,
)
from opord_builder.load import schema_index

# Reading order where the schemas' (alphabetical or authoring) order is not the doctrinal one.
HINTS: dict[str, tuple[str, ...]] = {
    "situation": (
        "area_of_interest",
        "area_of_operations",
        "enemy_forces",
        "friendly_forces",
        "interagency_intergovernmental_ngo",
        "interagency_organizations",
        "civil_considerations",
        "attachments_and_detachments",
        "assumptions",
    ),
    "situation.area_of_operations": ("summary", "terrain", "weather"),
    "situation.enemy_forces": (
        "summary",
        "recent_activities",
        "capabilities",
        "courses_of_action",
    ),
    "situation.friendly_forces": (
        "higher_two_levels",
        "higher_one_level",
        "adjacent_units",
        "other_units",
    ),
    "execution": (
        "commanders_intent",
        "concept_of_operations",
        "schemes",
        "*",
        "tasks_to_subordinate_units",
        "coordinating_instructions",
    ),
    "execution.commanders_intent": ("purpose", "key_tasks", "end_state"),
    "execution.concept_of_operations": ("summary", "overview"),
    "execution.coordinating_instructions": (
        "effective_time",
        "ccir",
        "eefi",
        "rules_of_engagement",
    ),
}
# Labels where the property name reads badly.
LABELS = {
    "situation.enemy_forces.summary": "Composition, Disposition, and Strength",
    "situation.area_of_operations.summary": "Description",
    "situation.area_of_operations.terrain": "Terrain (OAKOC)",
    "situation.interagency_intergovernmental_ngo": "Interagency, Intergovernmental, and Nongovernmental Organizations",
    "situation.civil_considerations": "Civil Considerations (ASCOPE)",
    "situation.enemy_forces.courses_of_action": "Courses of Action",
    "execution.commanders_intent": "Commander's Intent",
    "execution.tasks_to_subordinate_units": "Tasks to Subordinate Units",
    "execution.coordinating_instructions.ccir": "Commander's Critical Information Requirements (CCIR)",
    "execution.coordinating_instructions.eefi": "Essential Elements of Friendly Information (EEFI)",
    "execution.coordinating_instructions.rules_of_engagement": "Rules of Engagement",
    "sustainment.health_services": "Army Health System Support",
    "sustainment.personnel_services": "Personnel Services Support",
}
EXPAND = {
    "control_measures",
    "targets",
    "threats",
}  # catalogue lists that print their records, not their names
WIDE = 6  # columns; a wider table prints its first five and the rest as per-row details


@dataclass(frozen=True)
class Walk:
    """What a walk needs: the id lookup and the output format."""

    res: dict[str, dict[str, Any]]
    html: bool = False

    def name(self, kind: str | None, ident: str) -> str:
        rec = next(
            (
                m[ident]
                for k, m in self.res.items()
                if (kind is None or k == kind) and ident in m
            ),
            None,
        )
        return (
            str(rec.get("name") or rec.get("callsign") or ident)
            if isinstance(rec, dict)
            else ident
        )


# --------------------------------------------------------------------------- schemas


def is_keyed(node: dict) -> bool:
    branches = node.get("anyOf") or ()
    return (
        len(branches) == 2
        and "propertyNames" in branches[0]
        and branches[1].get("type") == "array"
    )


def deref(s: tuple[dict, dict] | None) -> tuple[dict, dict] | None:
    """Follow `$ref` (keeping sibling keywords such as `x-catalog`) and a single `allOf`."""
    while s and ("$ref" in s[0] or len(s[0].get("allOf", ())) == 1 or is_keyed(s[0])):
        node, root = s
        if is_keyed(
            node
        ):  # an array that the extension keys by item identifier: read it as the array
            s = (node["anyOf"][1], root)
        elif "$ref" in node:
            uri, _, frag = node["$ref"].partition("#")
            root = schema_index()[uri] if uri else root
            target: Any = root
            for part in frag.split("/")[1:]:
                target = target[part]
            s = ({**target, **{k: v for k, v in node.items() if k != "$ref"}}, root)
        else:
            s = (
                {**node["allOf"][0], **{k: v for k, v in node.items() if k != "allOf"}},
                root,
            )
    return s


def child(s: tuple[dict, dict] | None, key: str | None) -> tuple[dict, dict] | None:
    """The schema of property `key`, or of the items when `key` is None."""
    s = deref(s)
    if not s:
        return None
    node, root = s
    sub = node.get("items") if key is None else (node.get("properties") or {}).get(key)
    sub = sub or (node.get("additionalProperties") if key is not None else None)
    return deref((sub, root)) if isinstance(sub, dict) else None


def catalog(s: tuple[dict, dict] | None) -> str | None:
    return s[0].get("x-catalog") if s else None


# --------------------------------------------------------------------------- walking

Src = tuple[Any, "tuple[dict, dict] | None"]  # a value and its schema


def label_of(path: str, key: str) -> str:
    return LABELS.get(path, humanize(key) if key != "summary" else "Summary")


def ordered(srcs: list[Src], path: str, skip: set[str]) -> list[str]:
    """Keys in reading order: the hint, with `*` standing for the keys it does not name, in schema order."""
    rest: dict[str, None] = {}
    for value, sch in srcs:
        if isinstance(value, dict):
            props = list((deref(sch) or ({},))[0].get("properties", ()))
            rest.update(
                dict.fromkeys(
                    sorted(
                        value,
                        key=lambda k: props.index(k) if k in props else len(props),
                    )
                )
            )
    hint = HINTS.get(path, ("*",))
    keys = [
        k
        for h in (hint if "*" in hint else (*hint, "*"))
        for k in (rest if h == "*" else [h])
    ]
    present = {
        k
        for value, _ in srcs
        if isinstance(value, dict)
        for k, v in value.items()
        if has_content(v)
    }
    return [k for k in dict.fromkeys(keys) if k in present and k not in skip]


def is_shape(d: dict) -> bool:
    """A dict that `fmt` prints as one value (a position, an altitude, a window, ...)."""
    k = set(d)
    return bool(
        k <= {"value", "unit", "reference", "modulation", "band"}
        and k & {"value"}
        or {"latitude", "longitude"} <= k
        or {"lower", "upper"} <= k
        or {"start", "end"} <= k
        or {"channel", "band"} <= k
        or k in ({"surface"}, {"unlimited"}, {"offset_minutes"})
    )


def is_array(s: tuple[dict, dict] | None) -> bool:
    return bool(s) and deref(s)[0].get("type") == "array"


WEATHER = "situation.area_of_operations.weather"
LIGHT_HEAD = [
    "Date",
    "BMNT",
    "Sunrise",
    "Sunset",
    "EENT",
    "Moonrise",
    "Moonset",
    "Moon",
]
LIGHT_KEYS = [
    "begin_morning_nautical_twilight",
    "sunrise",
    "sunset",
    "end_evening_nautical_twilight",
    "moonrise",
    "moonset",
]


def weather_blocks(w: Walk, label: str, srcs: list[Src]) -> list:
    """The weather of the area of operations: its summary, a forecast table, a light table, and the extension's text."""
    openaix = [
        (v, s) for v, s in srcs if s and s[1].get("$id", "").startswith("urn:openaix")
    ]
    typed = openaix[0][0] if openaix else {}
    ext = next(((v, s) for v, s in srcs if (v, s) not in openaix), ({}, None))
    notes, days = ext[0].get("forecasts") or [], ext[0].get("light_data") or {}
    kids: list = (
        [("text", "Effects on Operations", typed["summary"])]
        if typed.get("summary")
        else []
    )
    rows = [
        forecast_row(f, notes[i] if i < len(notes) else {})
        for i, f in enumerate(typed.get("forecasts") or [])
    ]
    rows = rows or [forecast_row({}, n) for n in notes]
    cols = [c for c in FORECAST_HEAD if any(r[c] for r in rows)]
    if rows:
        kids.append(
            (
                "table",
                "Forecast",
                [FORECAST_HEAD[c] for c in cols],
                [[r[c] for c in cols] for r in rows],
            )
        )
    if typed.get("light_data"):
        light = []
        for d in typed["light_data"]:
            illum = (
                f"{d['moon_illumination_percent']}%"
                if "moon_illumination_percent" in d
                else ""
            )
            moon = " ".join(
                t for t in (days.get(d["date"], {}).get("moon_phase"), illum) if t
            )
            light.append(
                [d["date"], *(dtg(d[k]) if k in d else "" for k in LIGHT_KEYS), moon]
            )
        kids.append(("table", "Light Data", LIGHT_HEAD, light))
    rest = {k: v for k, v in ext[0].items() if k not in ("forecasts", "light_data")}
    if rest:
        kids += blocks(w, "weather", f"{WEATHER}.ext", [(rest, ext[1])])[0][2]
    return [("sec", label, kids)] if kids else []


def blocks(
    w: Walk, key: str, path: str, srcs: list[Src], skip: frozenset[str] = frozenset()
) -> list:
    """Blocks for the node `key` found in each source (typed document, extension) at `path`."""
    label = label_of(path, key)
    if path == WEATHER:
        return weather_blocks(w, label, srcs)
    srcs = [(v, s) for v, s in srcs if has_content(v)]
    if not srcs:
        return []
    values = [v for v, _ in srcs]
    if any(isinstance(v, list) or isinstance(v, dict) and is_array(s) for v, s in srcs):
        return listing(w, label, path, srcs)
    if all(isinstance(v, dict) and not is_shape(v) for v in values):
        inner = []
        for k in ordered(srcs, path, set(skip)):
            sub = [
                (v[k], child(s, k)) for v, s in srcs if isinstance(v, dict) and k in v
            ]
            inner += blocks(w, k, f"{path}.{k}", sub)
        if len(inner) == 1 and inner[0][:2] in (("kv", "Summary"), ("text", "Summary")):
            return [
                (inner[0][0], label, inner[0][2])
            ]  # a group that holds only its summary is that text
        return [("sec", label, inner)] if inner else []
    value, sch = srcs[0]
    text = cell(w, value, sch)
    return [("text" if len(text) > 100 or "\n" in text else "kv", label, text)]


def cell(w: Walk, value: Any, sch: tuple[dict, dict] | None) -> str:
    """One value as text; identifiers become the names of what they identify."""
    kind = catalog(sch)
    if isinstance(value, list):
        return "; ".join(t for t in (cell(w, v, child(sch, None)) for v in value) if t)
    if isinstance(value, str) and kind:
        return w.name(kind, value)
    if isinstance(value, dict) and not is_shape(value):
        if text := _one_text(value):
            return text
        return "; ".join(
            f"{humanize(k)}: {t}"
            for k, v in value.items()
            if k != "id" and (t := cell(w, v, child(sch, k)))
        )
    return fmt(value)


def record(rec: dict) -> dict:
    """A catalogue record as a row: no identifier or extension envelope, the opord-builder code as its type."""
    ext = (rec.get("extensions") or {}).get("org.opord-builder.measure") or {}
    row = {k: v for k, v in rec.items() if k not in ("id", "extensions")}
    if ext.get("code"):
        row["type"] = ext["code"]
    return {**row, **ext.get("extra", {})}


def rows_of(w: Walk, srcs: list[Src]) -> tuple[list[dict | str], tuple | None]:
    """The rows of a typed array with the extension's extra fields (keyed by item identifier) joined to them."""
    lists = [(v, s) for v, s in srcs if isinstance(v, list)]
    extras = next((v for v, _ in srcs if isinstance(v, dict)), {})
    items, sch = (
        (lists[0][0], child(lists[0][1], None))
        if lists
        else (None, child(srcs[0][1], None))
    )
    if items is None:  # only the extension has it: one row per identifier
        items = [{"name": w.name(None, k), **v} for k, v in extras.items()]
        extras = {}
    kind = catalog(sch)
    rows: list[dict | str] = []
    for item in items:
        ident = item.get("id") or item.get("unit") if isinstance(item, dict) else item
        extra = (extras.get(ident) if isinstance(ident, str) else None) or {}
        if isinstance(item, str) and (kind in EXPAND or extra):
            rec = w.res.get(kind or "", {}).get(item)
            item = {
                "name": item,
                **(record(rec) if isinstance(rec, dict) else {}),
                **extra,
            }
        elif isinstance(item, dict):
            item = {**item, **extra}
        rows.append(item)
    return rows, sch


def matrix(
    w: Walk, rows: list[dict], sch: tuple | None
) -> tuple[list[str], list[list[str]]]:
    """(column keys, text cells) of dict rows; empty columns and the identifier are left out."""
    cols = [
        c
        for c in dict.fromkeys(k for r in rows for k in r)
        if any(has_content(r.get(c)) for r in rows)
    ]
    if len(cols) > 1 and "id" in cols:
        cols.remove("id")
    return cols, [[cell(w, r.get(c), child(sch, c)) for c in cols] for r in rows]


def listing(w: Walk, label: str, path: str, srcs: list[Src]) -> list:
    """A table (or bullets) for an array; a table too wide for a page keeps its first columns and gets cards."""
    rows, sch = rows_of(w, srcs)
    if not any(isinstance(r, dict) for r in rows):
        return [("list", label, [cell(w, r, sch) for r in rows])]
    rows = [r if isinstance(r, dict) else {"": r} for r in rows]
    plain = [_one_text(r) for r in rows]
    if all(plain):  # {id, text}: just the text
        return [("list", label, plain)]
    cols, body = matrix(w, rows, sch)
    keep = WIDE - 1 if len(cols) > WIDE else len(cols)
    out: list = [
        ("table", label, [humanize(c) for c in cols[:keep]], [r[:keep] for r in body])
    ]
    if len(cols) > keep:
        out.append(
            (
                "cards",
                [
                    (
                        r[0] or "-",
                        [(humanize(c), t) for c, t in zip(cols[keep:], r[keep:]) if t],
                    )
                    for r in body
                ],
            )
        )
    return out


def _one_text(row: dict) -> str:
    rest = {k: v for k, v in row.items() if k != "id" and has_content(v)}
    only = next(iter(rest.values())) if len(rest) == 1 else None
    return only if isinstance(only, str) else ""


# --------------------------------------------------------------------------- emitters


def marks(level: int, n: int, num: str, annex: bool) -> tuple[str, str]:
    """(mark, shown): doctrinal numbering `3.a.` / `3.a.(1)` under a paragraph, `1.` in an annex."""
    if annex:
        return (f"{n}.", f"{n}.") if level == 1 else ("", "")
    if not num:
        return "", ""
    if level == 1:
        return f"{num}.{letter_for(n)}", f"{num}.{letter_for(n)}."
    return (f"{num}.({n})",) * 2 if level == 2 else ("", "")


def cellmd(t: str) -> str:
    return t.replace("|", r"\|").replace("\n", " ")


def md(blks: list, level: int = 1, num: str = "", annex: bool = False) -> str:
    """Markdown."""
    out = []
    for n, b in enumerate(blks, 1):
        mark, shown = marks(level, n, num, annex)
        kind = b[0]
        label = b[1] if kind != "cards" else None
        head = f"{shown} {label}".strip() if label else shown
        if kind == "sec":
            if shown and not annex and level == 1:
                top = f"### {head}"
            elif shown and not annex:
                top = f"#### {head}"
            else:
                top = f"**{head}**"
            out.append(f"{top}\n\n" + md(b[2], level + 1, mark, annex))
        elif kind in ("text", "kv"):
            text = b[2]
            if not label:
                out.append(text + "\n")
            elif shown and not annex and level == 1:
                out.append(f"### {head}\n\n{text}\n")
            elif shown and not annex:
                out.append(f"**{head}.** {text}\n")
            elif "\n\n" in text:
                out.append(f"**{head}**\n\n{text}\n")
            else:
                out.append(f"- **{head}:** {text}")
        elif kind == "list":
            out.append(f"**{head}**\n\n" + "\n".join(f"- {t}" for t in b[2]) + "\n")
        elif kind == "table":
            rule = "|" + "|".join("---" for _ in b[2]) + "|\n"
            rows = "\n".join(
                "| " + " | ".join(cellmd(c) for c in r) + " |" for r in b[3]
            )
            out.append(
                f"**{head}**\n\n| " + " | ".join(b[2]) + " |\n" + rule + rows + "\n"
            )
        else:
            out.append(
                "\n\n".join(
                    f"**{t}**\n" + "\n".join(f"- **{k}:** {cellmd(v)}" for k, v in rows)
                    for t, rows in b[1]
                )
                + "\n"
            )
    lines: list[str] = []
    for chunk in out:
        if lines and lines[-1].startswith("- ") and not chunk.startswith("- "):
            lines.append("")
        lines.append(chunk)
    return "\n".join(lines)


def html(blks: list, level: int = 1, num: str = "", annex: bool = False) -> str:
    """HTML in the `tb-*` classes."""
    out = []
    for n, b in enumerate(blks, 1):
        mark, shown = marks(level, n, num, annex)
        kind = b[0]
        label = ""
        if kind != "cards" and b[1]:
            label = (
                f'<span class="tb-num">{escape(shown)}</span> ' if shown else ""
            ) + escape(b[1])
        head = f'<div class="tb-field-label">{label}</div>' if label else ""
        if kind == "sec":
            out.append(
                f'<div class="tb-table-block">{head}<div class="typed-body">{html(b[2], level + 1, mark, annex)}</div></div>'
            )
        elif kind == "text":
            body = "".join(f"<p>{escape(p)}</p>" for p in paragraphs(b[2]))
            field = f'<div class="tb-field">{head}<div class="tb-field-body">{body}</div></div>'
            out.append(field if head else f'<div class="tb-field-body">{body}</div>')
        elif kind == "kv":
            out.append(
                f'<div class="tb-kv"><span class="tb-kv-k">{label}:</span> <span class="tb-kv-v">{escape(b[2])}</span></div>'
            )
        elif kind == "list":
            items = "".join(f"<li>{escape(t)}</li>" for t in b[2])
            out.append(
                f'<div class="tb-field">{head}<ul class="tb-list">{items}</ul></div>'
            )
        elif kind == "table":
            top = "".join(f"<th>{escape(c)}</th>" for c in b[2])
            rows = "".join(
                "<tr>" + "".join(f"<td>{escape(c)}</td>" for c in r) + "</tr>"
                for r in b[3]
            )
            out.append(
                f'<div class="tb-table-block">{head}<table class="tb-table"><thead><tr>{top}</tr></thead><tbody>{rows}</tbody></table></div>'
            )
        else:
            row = lambda k, v: (
                f'<div class="tb-detail-row"><span class="tb-detail-k">{escape(k)}</span><span class="tb-detail-v">{escape(v)}</span></div>'
            )
            cards = "".join(
                f'<div class="tb-detail-entry"><div class="tb-detail-head"><span class="tb-detail-id">{escape(t)}</span></div>'
                f'<div class="tb-detail-body">{"".join(row(k, v) for k, v in rows)}</div></div>'
                for t, rows in b[1]
            )
            out.append(f'<div class="tb-detail-list">{cards}</div>')
    return "".join(out)


def render(
    w: Walk,
    key: str,
    srcs: list[Src],
    num: str = "",
    skip: frozenset[str] = frozenset(),
) -> str:
    """The content of one paragraph as Markdown or HTML ('' when it has none)."""
    blks = blocks(w, key, key, srcs, skip)
    inner = blks[0][2] if blks and blks[0][0] == "sec" else blks
    return (html if w.html else md)(inner, 1, num)
