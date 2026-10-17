"""Generated schema documents: single-file bundled schemas, the complete-schema page and the annex reference.

Everything here is pure and deterministic: `generated()` maps repo-relative paths to text, `opord docs` writes them
and `opord docs --check` compares them with the disk.
"""

from __future__ import annotations

import copy
import html
import json
import re
from functools import cache
from pathlib import Path
from typing import Any

from opord_builder.load import NS, schema_index

ROOT = Path(__file__).resolve().parent.parent
KINDS = ("opord", "frago", "spins", "ato", "resources")
EXT_ID = "urn:opord-builder:extension:{}:1"
# Extension -> where the bundle for a document kind plugs it in: (definition or None for the root).
PLUGS = {
    "opord": [("order", None), ("kneeboard", None), ("data", None)],
    "frago": [("order", None), ("kneeboard", None), ("data", None)],
    "spins": [("spins", None), ("data", None)],
    "ato": [("kneeboard", None), ("kneeboard", "Flight"), ("data", None)],
    "resources": [("resources", None), ("data", None)],
}


# --------------------------------------------------------------------------- sources


def short(schema_id: str) -> str:
    """`urn:openaix:schema:measure-aca:0.2.0-draft.1` -> `measure-aca`; an extension `...:extension:order:1` -> `ext-order`."""
    parts = schema_id.split(":")
    return ("ext-" if parts[1] == "opord-builder" else "") + parts[3]


@cache
def sources() -> dict[str, dict[str, Any]]:
    """Short name -> schema, for the vendored schemas and the extensions (the SPINS one regenerated from its model)."""
    out = {short(i): s for i, s in schema_index().items()}
    try:
        from opord_builder.schema.spins import spins_extension_schema
    except ImportError:  # pragma: no cover
        return out
    out["ext-spins"] = spins_extension_schema()
    return out


def measure_shorts() -> set[str]:
    """The control-measure schemas: the whole-schema alternatives of `common#/$defs/ControlMeasure`."""
    alts = sources()["common"]["$defs"]["ControlMeasure"]["oneOf"]
    return {short(a["$ref"]) for a in alts if "$ref" in a}


# --------------------------------------------------------------------------- bundles


def _ref(ref: str, here: str, root: str, need: set[str]) -> str:
    base, _, frag = ref.partition("#")
    target = short(base) if base else here
    need.add(target)
    if not frag:
        return "#" if target == root else f"#/$defs/{target}"
    m = re.fullmatch(r"/\$defs/([^/]+)(.*)", frag)
    assert m, f"unsupported $ref fragment {ref!r}"
    name = m[1] if target == root else f"{target}.{m[1]}"
    return f"#/$defs/{name}{m[2]}"


def _rewrite(node: Any, here: str, root: str, need: set[str]) -> Any:
    if isinstance(node, list):
        return [_rewrite(n, here, root, need) for n in node]
    if not isinstance(node, dict):
        return node
    return {
        k: _ref(v, here, root, need)
        if k == "$ref" and isinstance(v, str)
        else _rewrite(v, here, root, need)
        for k, v in node.items()
    }


def _plug(schema: dict, plugs: list[tuple[str, str | None]]) -> None:
    for ext, definition in plugs:
        target = (
            schema if definition is None else schema.get("$defs", {}).get(definition)
        )
        holder = ((target or {}).get("properties") or {}).get("extensions")
        if holder is not None:
            holder.setdefault("properties", {})[NS + ext] = {"$ref": EXT_ID.format(ext)}


BINDING = {"type": "string", "pattern": r"^\$\{[^}]+\}$"}


def _bindable(node: Any) -> Any:
    """Let a `${...}` binding stand wherever a value goes: each schema under `properties`, `additionalProperties`,
    `items` and `prefixItems` becomes `anyOf: [schema, Binding]`. The data group is left alone."""

    def wrap(sub: Any) -> Any:
        sub = _bindable(sub)
        if not isinstance(sub, dict):
            return sub
        inner = {
            k: v for k, v in sub.items() if k != "description"
        }  # the wrapper carries it
        out = {"anyOf": [inner, {"$ref": "#/$defs/Binding"}]}
        return (
            {"description": sub["description"], **out} if "description" in sub else out
        )

    if not isinstance(node, dict):
        return node
    out = {}
    for k, v in node.items():
        if k in ("properties", "patternProperties") and isinstance(v, dict):
            out[k] = {
                n: sub
                if n == NS + "data"
                else wrap(sub)
                if k == "properties"
                else _bindable(sub)
                for n, sub in v.items()
            }
        elif k == "$defs" and isinstance(v, dict):
            out[k] = {
                n: sub if n == "data" or n.startswith("data.") else _bindable(sub)
                for n, sub in v.items()
            }
        elif (
            k == "additionalProperties"
            and isinstance(v, dict)
            or k == "items"
            and isinstance(v, dict)
        ):
            out[k] = wrap(v)
        elif k == "prefixItems" and isinstance(v, list):
            out[k] = [wrap(x) for x in v]
        elif k in ("allOf", "anyOf", "oneOf") and isinstance(v, list):
            out[k] = [_bindable(x) for x in v]
        elif k in ("not", "if", "then", "else", "contains"):
            out[k] = _bindable(v)
        else:
            out[k] = v
    return out


def bundled(kind: str, strict: bool = False) -> dict[str, Any]:
    """A single-file JSON Schema for `kind`: urn refs inlined into `$defs`, the extension schemas plugged in.
    Unless `strict`, a `${...}` binding is accepted in any value; `strict` is for resolved documents."""
    assert kind in KINDS, kind
    pool, measures = sources(), measure_shorts()
    defs: dict[str, Any] = {}
    done: set[str] = set()
    todo = [kind]
    root_body: dict[str, Any] = {}
    while todo:
        name = todo.pop()
        if name in done:
            continue
        done.add(name)
        schema = copy.deepcopy(pool[name])
        _plug(
            schema,
            PLUGS[kind]
            if name == kind
            else [("measure", None)]
            if name in measures
            else [],
        )
        need: set[str] = set()
        body = {k: v for k, v in schema.items() if k not in ("$id", "$schema", "$defs")}
        body = _rewrite(body, name, kind, need)
        for def_name, sub in schema.get("$defs", {}).items():
            key = def_name if name == kind else f"{name}.{def_name}"
            defs[key] = _rewrite(sub, name, kind, need)
        if name == kind:
            root_body = body
        else:
            defs[name] = body
        todo += sorted(need - done)
    out = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"urn:opord-builder:bundled:{kind}",
        **root_body,
        "$defs": dict(sorted(defs.items())),
    }
    if strict:
        return out
    out = _bindable(out)
    out["$defs"] = dict(sorted({**out["$defs"], "Binding": BINDING}.items()))
    return out


# --------------------------------------------------------------------------- HTML helpers

CSS = (
    ":root{--ink:#20272c;--muted:#626d75;--line:#dce1e4;--wash:#f5f7f8;--link:#195a78}"
    "*{box-sizing:border-box}html{scroll-padding-top:12px}"
    "body{margin:0;color:var(--ink);background:#fff;font:15px/1.55 system-ui,-apple-system,'Segoe UI',sans-serif}"
    "a{color:var(--link);text-underline-offset:3px}code{font:13px ui-monospace,Menlo,Consolas,monospace;background:var(--wash);padding:0 3px}"
    "aside{position:fixed;inset:0 auto 0 0;width:250px;padding:22px 16px;background:var(--wash);border-right:1px solid var(--line);overflow:auto}"
    "aside h2{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:22px 0 6px}"
    "aside a{display:block;text-decoration:none;padding:3px 8px;overflow-wrap:anywhere}aside a:hover{background:#e8edf0}"
    "main{margin-left:250px;max-width:1400px;padding:30px 40px 80px}.page{max-width:1100px;margin:0 auto;padding:30px 24px 80px}"
    "h1{font-size:30px;margin:0 0 8px}h2.kind{font-size:24px;margin:44px 0 6px;border-top:2px solid var(--line);padding-top:18px}"
    "h3{font-size:17px;margin:26px 0 6px}.sub{color:var(--muted);font-size:13px}"
    "table{border-collapse:collapse;width:100%;margin:8px 0}th,td{border:1px solid var(--line);padding:6px 9px;vertical-align:top;text-align:left}"
    "th{background:var(--wash);font-size:12px;text-transform:uppercase;letter-spacing:.05em}td.n{white-space:nowrap}"
    "ul.enum{margin:6px 0 0;padding-left:18px}.req{font-weight:700}"
    "@media(max-width:800px){aside{position:static;width:auto}main{margin:0;padding:20px 14px}}"
)


def _text(value: str) -> str:
    return re.sub(
        r"`([^`]+)`", r"<code>\1</code>", html.escape(value or "", quote=False)
    )


def _anchor(schema_name: str, def_name: str | None = None) -> str:
    return schema_name if def_name is None else f"{schema_name}.{def_name}"


def _link(ref: str, here: str, base: str) -> str:
    b, _, frag = ref.partition("#")
    target = short(b) if b else here
    m = re.match(r"/\$defs/([^/]+)(/properties/(.+))?", frag)
    name = _anchor(target, m[1] if m else None)
    label = (m[1] + ("." + m[3] if m[3] else "")) if m else target
    return f'<a href="{base}#{html.escape(name)}">{html.escape(label)}</a>'


def type_html(s: dict, here: str, base: str = "") -> str:
    """The type of a (sub)schema as HTML, with links to other types."""
    if not isinstance(s, dict):
        return "any"
    if "$ref" in s:
        return _link(s["$ref"], here, base)
    if "const" in s:
        return f"<code>{html.escape(json.dumps(s['const']))}</code>"
    for key, sep in (("oneOf", " | "), ("anyOf", " | "), ("allOf", " &amp; ")):
        if key in s:
            return sep.join(type_html(x, here, base) for x in s[key])
    t = s.get("type")
    if "enum" in s:
        return "enum"
    if t == "array":
        return "list of " + type_html(s.get("items", {}), here, base)
    if t == "object" and isinstance(s.get("additionalProperties"), dict):
        return "map of " + type_html(s["additionalProperties"], here, base)
    label = "/".join(t) if isinstance(t, list) else (t or "any")
    return label + (f" ({html.escape(s['format'])})" if "format" in s else "")


def enum_html(s: dict) -> str:
    """Enum values with their descriptions: `x-enum-descriptions`, or `oneOf` entries of `const` + `description`."""
    if "enum" not in s and "oneOf" not in s and isinstance(s.get("items"), dict):
        s = s["items"]
    notes = s.get("x-enum-descriptions", {})
    pairs = [(v, notes.get(str(v), "")) for v in s.get("enum", [])]
    pairs += [
        (x["const"], x.get("description", ""))
        for x in s.get("oneOf", [])
        if "const" in x
    ]
    if not pairs:
        return ""
    items = "".join(
        f"<li><code>{html.escape(str(v))}</code>{' ' + _text(d) if d else ''}</li>"
        for v, d in pairs
    )
    return f'<ul class="enum">{items}</ul>'


def fields_table(s: dict, here: str, base: str = "") -> str:
    props = s.get("properties") or {}
    if not props:
        return ""
    required = set(s.get("required", []))
    rows = "".join(
        f'<tr><td class="n"><code>{html.escape(n)}</code></td><td>{type_html(p, here, base)}</td>'
        f"<td>{'<span class=req>yes</span>' if n in required else ''}</td>"
        f"<td>{_text(p.get('description', ''))}{enum_html(p)}</td></tr>"
        for n, p in props.items()
    )
    return f"<table><tr><th>Field</th><th>Type</th><th>Required</th><th>Description</th></tr>{rows}</table>"


def type_card(
    anchor: str, label: str, s: dict, here: str, level: int = 3, base: str = ""
) -> str:
    table = fields_table(s, here, base)
    summary = (
        ""
        if table
        else f'<p class="sub">Type: {type_html(s, here, base)}</p>{enum_html(s)}'
    )
    return (
        f'<h{level} id="{html.escape(anchor)}">{html.escape(label)}</h{level}>'
        f"<p>{_text(s.get('description', ''))}</p>{table}{summary}"
    )


# --------------------------------------------------------------------------- complete schema


def _groups() -> list[tuple[str, list[str]]]:
    pool = sources()
    docs = list(KINDS)
    ext = sorted(n for n in pool if n.startswith("ext-"))
    measures = sorted(n for n in pool if n.startswith("measure-"))
    rest = sorted(set(pool) - set(docs) - set(ext) - set(measures))
    return [
        ("Documents", docs),
        ("Supporting", rest),
        ("Measures", measures),
        ("Extensions", ext),
    ]


def complete_schema_html() -> str:
    pool, groups = sources(), _groups()
    nav = "".join(
        f"<h2>{g}</h2>" + "".join(f'<a href="#{n}">{n}</a>' for n in names)
        for g, names in groups
    )
    body = []
    for _, names in groups:
        for name in names:
            s = pool[name]
            body.append(f'<h2 class="kind">{html.escape(s.get("title", name))}</h2>')
            body.append(f'<p class="sub"><code>{html.escape(s["$id"])}</code></p>')
            body.append(type_card(name, name, s, name, 3))
            for def_name, sub in s.get("$defs", {}).items():
                body.append(type_card(_anchor(name, def_name), def_name, sub, name, 4))
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Complete schema reference</title><style>{CSS}</style></head><body>"
        f"<aside><strong>OpenAIX schemas</strong><div class=sub>and the opord-builder extensions</div>{nav}</aside>"
        f"<main><h1>Complete schema reference</h1><p>Every vendored OpenAIX schema and every "
        f"<code>{NS}*</code> extension schema. Each type has a field table. Generated by <code>opord docs</code>; do not edit.</p>"
        f"{''.join(body)}</main></body></html>\n"
    )


# --------------------------------------------------------------------------- annex reference

RESERVED = "IOTXY"


def reference_html() -> str:
    opord = sources()["opord"]
    defs, annexes = opord["$defs"], opord["$defs"]["Annexes"]["properties"]
    base = "complete-schema.html"
    sections, toc = [], []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if letter in RESERVED:
            toc.append(f"<li>{letter} (reserved)</li>")
            continue
        prop = annexes[letter]
        name = prop["$ref"].rsplit("/", 1)[-1]
        title = re.sub(r"(?<!^)(?=[A-Z])", " ", name).replace(" Annex", "")
        toc.append(
            f'<li><a href="#annex-{letter}">{letter}: {html.escape(title)}</a></li>'
        )
        part = [
            f'<h2 id="annex-{letter}">Annex {letter}: {html.escape(title)}</h2>',
            f"<p>{_text(prop.get('description', ''))}</p>",
            type_card(f"annex-{letter}-{name}", name, defs[name], "opord", 3, base),
        ]
        for field in defs[name].get("properties", {}).values():
            ref = field.get("$ref", "").rsplit("/", 1)[-1]
            if ref.endswith("Appendix") and ref in defs:
                part.append(
                    type_card(f"annex-{letter}-{ref}", ref, defs[ref], "opord", 3, base)
                )
        sections.append("".join(part))
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Annex reference</title><style>{CSS}</style></head><body><div class=page>"
        "<h1>Annex reference</h1><p>The annexes of an OpenAIX <code>opord</code>, by letter, from the "
        f'<code>Annexes</code> definition. Types link to the <a href="{base}">complete schema reference</a>. '
        f"Generated by <code>opord reference</code>; do not edit.</p><ul>{''.join(toc)}</ul>"
        f"{''.join(sections)}</div></body></html>\n"
    )


# --------------------------------------------------------------------------- everything


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def generated() -> dict[Path, str]:
    """Every generated file: repo-relative path -> text."""
    out = {
        Path("docs/complete-schema.html"): complete_schema_html(),
        Path("docs/annex_reference.html"): reference_html(),
    }
    out |= {Path(f"schemas/bundled/{k}.schema.json"): _json(bundled(k)) for k in KINDS}
    out[Path("schemas/extensions/spins.schema.json")] = _json(sources()["ext-spins"])
    return out
