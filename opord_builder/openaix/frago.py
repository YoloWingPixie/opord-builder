"""FRAGO <-> OpenAIX `frago`.

Export. The YAML FRAGO is a sparse overlay on its base OPORD. We (1) convert the base, (2) apply the overlay to
the base model (a paragraph is merged field by field; lists and scalars replace; an annex replaces the annex of
the same letter), (3) convert the result, and (4) diff the two OpenAIX documents at paragraph granularity into
`replace` / `add` / `remove` changes at depth 2 (for example `/execution/coordinating_instructions`,
`/annexes/C`, `/mission/statement`) or depth 3 under `/extensions`. Arrays are replaced whole. The base is the
`OrderRef{id, revision}` of the converted base.

Import reverses it: the base revision must match (`StaleBaseError` otherwise), the changes are applied to the
converted base, the merged document is read back to a model, and the overlay is rebuilt from the paths the FRAGO
touched (recorded in the authoring extension as `@overlay`, or computed as a sparse diff for a FRAGO written by
another tool), so the renderer's "No change" stubs still work.

Deviation from the spec text: `opord_builder/merge.py` only resolves data-source bindings and cannot overlay a
FRAGO, so the overlay merge lives here (`merge_overlay`).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from opord_builder.openaix import _mapping as mp
from opord_builder.openaix import convert as c
from opord_builder.openaix._engine import (
    AUTHORING_NS,
    MISSING,
    Ctx,
    flatten,
    get_path,
    group_stash,
    ptr_get,
    ptr_set,
    set_path,
    sorted_paths,
    ungroup_stash,
)
from opord_builder.openaix.registry import schemas
from opord_builder.openaix.to_openaix import OpenAIXExportError, to_openaix
from opord_builder.openaix.validate import validate
from opord_builder.schema.core import FRAGO, OPORD

PARAGRAPHS = (
    "situation",
    "mission",
    "execution",
    "sustainment",
    "command_and_signal",
    "authentication",
)
HEADER_KEYS = {
    "kind",
    "frago_number",
    "base_order",
    "previous_fragos",
    "classification",
    "classification_caveat",
    "issuing_headquarters",
    "place_of_issue",
    "dtg",
    "time_zone",
    "copy_number",
    "number_of_copies",
    "author",
}


class StaleBaseError(ValueError):
    """The FRAGO was written against a different revision of the base order than the one supplied."""


class FragoChangeError(ValueError):
    """A change in the FRAGO cannot be applied to the base."""


@dataclass
class FragoBundle:
    frago: dict[str, Any]
    resources: dict[str, Any] | None = (
        None  # merged resources, only when the FRAGO changes measures or channels
    )
    jiptl: dict[str, Any] | None = (
        None  # merged JPITL document, only when the FRAGO changes it
    )
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- overlay on the model dump


def merge_overlay(
    base: dict[str, Any], over: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """(merged dump, touched paths). Dicts merge key by key; any other value replaces. `annexes` replace by
    letter (path `annexes.<letter>`). Paths are dotted."""
    merged = copy.deepcopy(base)
    touched: list[str] = []

    def walk(b: dict, o: dict, prefix: str) -> None:
        for k, v in o.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict) and isinstance(b.get(k), dict):
                walk(b[k], v, path)
            elif isinstance(v, dict) and not v or v in ([], None):
                continue
            else:
                b[k] = copy.deepcopy(v)
                touched.append(path)

    for key in PARAGRAPHS + ("kneeboards",):
        if key not in over:
            continue
        v = over[key]
        if key == "mission" or key == "kneeboards" or not isinstance(v, dict):
            if v:
                merged[key] = copy.deepcopy(v)
                touched.append(key)
        elif v:
            if isinstance(merged.get(key), dict):
                walk(merged[key], v, key)
            else:
                merged[key] = copy.deepcopy(v)
                touched.append(key)
    if over.get("annexes"):
        annexes = merged.setdefault("annexes", [])
        for a in over["annexes"]:
            idx = next(
                (i for i, x in enumerate(annexes) if x["letter"] == a["letter"]), None
            )
            if idx is None:
                annexes.append(copy.deepcopy(a))
            else:
                annexes[idx] = copy.deepcopy(a)
            touched.append(f"annexes.{a['letter']}")
        annexes.sort(key=lambda x: x["letter"])
    return merged, touched


def sparse_touched(base: dict[str, Any], merged: dict[str, Any]) -> list[str]:
    """Paths where `merged` differs from `base`, in the granularity merge_overlay records."""
    out: list[str] = []

    def walk(b: Any, m: Any, path: str) -> None:
        if b == m:
            return
        if isinstance(b, dict) and isinstance(m, dict):
            for k, v in m.items():
                walk(b.get(k, MISSING), v, f"{path}.{k}")
        else:
            out.append(path)

    for key in PARAGRAPHS + ("kneeboards",):
        if merged.get(key) != base.get(key) and merged.get(key) is not None:
            if key in ("mission", "kneeboards") or not isinstance(merged[key], dict):
                out.append(key)
            else:
                for k, v in merged[key].items():
                    walk((base.get(key) or {}).get(k, MISSING), v, f"{key}.{k}")
    b_annex = {a["letter"]: a for a in base.get("annexes", [])}
    for a in merged.get("annexes", []):
        if b_annex.get(a["letter"]) != a:
            out.append(f"annexes.{a['letter']}")
    return out


def _overlay_from(merged: dict[str, Any], touched: list[str]) -> dict[str, Any]:
    over: dict[str, Any] = {}
    for path in touched:
        if path.startswith("annexes."):
            letter = path.split(".", 1)[1]
            annex = next(
                (a for a in merged.get("annexes", []) if a["letter"] == letter), None
            )
            if annex is not None:
                over.setdefault("annexes", []).append(copy.deepcopy(annex))
            continue
        v = get_path(merged, path)
        if v is not MISSING:
            set_path(over, path, copy.deepcopy(v))
    return over


# --------------------------------------------------------------------------- diff and apply


def _esc(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def diff_documents(base: dict, merged: dict) -> list[tuple[str, str, Any]]:
    """[(op, pointer, value)] from `base` to `merged`; depth 2, or 3 under /extensions. Lists replace whole."""
    out: list[tuple[str, str, Any]] = []

    def walk(b: Any, m: Any, path: tuple[str, ...]) -> None:
        if b == m:
            return
        limit = 3 if path[:1] == ("extensions",) else 2
        if len(path) < limit and isinstance(b, dict) and isinstance(m, dict):
            for k, v in m.items():
                if k not in b:
                    out.append(
                        (
                            "add",
                            "/" + "/".join(_esc(x) for x in (*path, k)),
                            copy.deepcopy(v),
                        )
                    )
                else:
                    walk(b[k], v, (*path, k))
            for k in b:
                if k not in m:
                    out.append(
                        ("remove", "/" + "/".join(_esc(x) for x in (*path, k)), None)
                    )
        else:
            out.append(
                ("replace", "/" + "/".join(_esc(x) for x in path), copy.deepcopy(m))
            )

    walk(base, merged, ())
    return out


def _unesc(key: str) -> str:
    return key.replace("~1", "/").replace("~0", "~")


def apply_changes(doc: dict, changes: list[dict]) -> dict:
    """Apply OrderChange items (add / replace / remove at a JSON Pointer) to a copy of `doc`."""
    out = copy.deepcopy(doc)
    for ch in changes:
        keys = [_unesc(k) for k in ch["path"].split("/")[1:]]
        node = out
        for k in keys[:-1]:
            try:
                node = node[int(k) if isinstance(node, list) else k]
            except (KeyError, IndexError, ValueError) as exc:
                raise FragoChangeError(
                    f"{ch['path']}: parent path not found in the base"
                ) from exc
        last = keys[-1]
        op = ch["op"]
        try:
            if isinstance(node, list):
                idx = len(node) if last == "-" else int(last)
                if op == "add":
                    node.insert(idx, copy.deepcopy(ch["value"]))
                elif op == "replace":
                    node[idx] = copy.deepcopy(ch["value"])
                else:
                    del node[idx]
            elif op == "remove":
                del node[last]
            else:
                if op == "replace" and last not in node:
                    raise FragoChangeError(
                        f"{ch['path']}: replace target is not in the base"
                    )
                node[last] = copy.deepcopy(ch["value"])
        except (KeyError, IndexError) as exc:
            raise FragoChangeError(
                f"{ch['path']}: {op} target not found in the base"
            ) from exc
    return out


# --------------------------------------------------------------------------- export


def _header_leaves() -> list[Any]:
    L = mp.Leaf
    pp = mp.PRINT_PTR
    return [
        L("frago_number", "/frago_number"),
        L(
            "classification",
            "/meta/classification",
            mp.to_classification,
            mp.from_classification,
        ),
        L("classification_caveat", f"{pp}/classification_caveat"),
        L("issuing_headquarters", "/issuing_headquarters"),
        L("place_of_issue", f"{pp}/place_of_issue"),
        L("dtg", "/date_time", mp.to_dtg_rfc, mp.from_rfc_dtg),
        L("time_zone", "/time_zone", mp.to_zone, mp.from_zone),
        L("copy_number", f"{pp}/copy_number", mp.positive_int),
        L("number_of_copies", f"{pp}/number_of_copies", mp.positive_int),
        L("author", "/meta/author"),
    ]


def _split(frago: FRAGO) -> tuple[dict[str, Any], dict[str, Any]]:
    dump = frago.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    over = {
        k: dump.pop(k)
        for k in list(dump)
        if k in PARAGRAPHS + ("annexes", "kneeboards")
    }
    return dump, over


def _overlay_model_dump(base: OPORD, frago: FRAGO) -> tuple[OPORD, list[str]]:
    base_d = base.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    _, over = _split(frago)
    merged_d, touched = merge_overlay(base_d, over)
    return OPORD.model_validate(merged_d), touched


def frago_to_openaix(frago: FRAGO, base: OPORD, *, check: bool = True) -> FragoBundle:
    base_b = to_openaix(base, check=False)
    merged, touched = _overlay_model_dump(base, frago)
    merged_b = to_openaix(merged, check=False)
    base_doc, merged_doc = base_b.opord, merged_b.opord
    ref = {"id": base_doc["meta"]["id"], "revision": base_doc["meta"]["revision"]}

    header, _ = _split(frago)
    header.pop("kind", None)
    ctx = Ctx()
    ctx.doc = {
        "$schema": schemas()["frago"]["$id"],
        "kind": "frago",
        "schema_version": mp.schema_version(),
    }
    for leaf in _header_leaves():
        leaf.enc(header, ctx)
    for k, v in flatten(header, ctx.typed_lists).items():
        ctx.stash.setdefault(k, v)
    doc = ctx.doc
    number = doc.get("frago_number", "00")
    meta = doc.setdefault("meta", {})
    meta.setdefault("id", c.slug(f"{ref['id']} frago {number}"))
    meta.setdefault("revision", "1")
    meta.setdefault(
        "title", f"FRAGO {number} to {base_doc['meta'].get('title') or ref['id']}"
    )
    meta["references"] = [{"id": ref["id"], "revision": ref["revision"]}]
    doc["meta"] = dict(sorted(meta.items()))
    doc["base_order"] = ref
    doc["references"] = [{"id": ref["id"], "revision": ref["revision"]}]
    if frago.mission:
        doc["mission"] = frago.mission
    target = {"kind": "opord", **ref}
    doc["changes"] = [
        {
            "op": op,
            "path": path,
            "target": dict(target),
            **({"value": value} if op != "remove" else {}),
        }
        for op, path, value in diff_documents(base_doc, merged_doc)
    ]
    ptr_set(
        doc,
        f"/extensions/{AUTHORING_NS}",
        {**group_stash(ctx.stash), "@overlay": touched},
    )
    resources = merged_b.resources if merged_b.resources != base_b.resources else None
    if check:
        errors = validate(doc) + (validate(resources) if resources else [])
        if errors:
            raise OpenAIXExportError(errors)
    jiptl = merged_b.jiptl if merged_b.jiptl != base_b.jiptl else None
    if check and jiptl:
        errors = validate(jiptl)
        if errors:
            raise OpenAIXExportError(errors)
    return FragoBundle(
        doc, resources, jiptl, [*base_b.warnings, *merged_b.warnings, *ctx.warnings]
    )


# --------------------------------------------------------------------------- import


def frago_from_openaix(
    doc: dict[str, Any],
    base: OPORD,
    *,
    resources: dict[str, Any] | None = None,
    jiptl: dict[str, Any] | None = None,
    base_order: str | None = None,
) -> tuple[FRAGO, list[str]]:
    """(FRAGO, warnings). `base` is the base OPORD model; `base_order`, when given, is the path to write into the
    YAML FRAGO (it wins over the path the document records)."""
    if not isinstance(doc, dict) or doc.get("kind") != "frago":
        raise ValueError("not an OpenAIX frago document (kind must be 'frago')")
    errors = validate(doc)
    if errors:
        raise ValueError(
            "input does not validate against the vendored schema:\n"
            + "\n".join(f"  {e}" for e in errors[:20])
        )
    base_b = to_openaix(base, check=False)
    ref = ptr_get(doc, "/base_order")
    have = {
        "id": base_b.opord["meta"]["id"],
        "revision": base_b.opord["meta"]["revision"],
    }
    if ref is not MISSING and ref != have:
        raise StaleBaseError(
            f"FRAGO is written against base {ref['id']!r} revision {ref['revision']!r}, "
            f"but the base order is {have['id']!r} revision {have['revision']!r}"
        )
    changes = doc.get("changes", [])
    for ch in changes:
        t = ch["target"]
        if t["kind"] != "opord" or {"id": t["id"], "revision": t["revision"]} != have:
            raise StaleBaseError(
                f"change {ch['path']} targets {t['kind']} {t['id']!r} revision {t['revision']!r}, "
                f"not the base order {have['id']!r} revision {have['revision']!r}"
            )
    from opord_builder.openaix.from_openaix import from_openaix

    merged_doc = apply_changes(base_b.opord, changes)
    merged, warnings = from_openaix(
        merged_doc,
        resources or base_b.resources,
        jiptl or base_b.jiptl,
        carry=False,
        check=False,
    )

    ctx = Ctx(warnings=warnings)
    stash, special = ungroup_stash(
        ptr_get(doc, f"/extensions/{AUTHORING_NS}", {}) or {}
    )
    touched = special.get("@overlay")
    d: dict[str, Any] = {"kind": "frago"}
    for leaf in _header_leaves():
        leaf.dec(doc, d, ctx)
    for key in sorted_paths(stash):
        set_path(d, key, stash[key])
    base_d = base.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    merged_d = merged.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    if touched is None:
        touched = sparse_touched(base_d, merged_d)
    d.update(_overlay_from(merged_d, touched))
    if base_order is not None:
        d["base_order"] = base_order
    elif "base_order" not in d:
        raise ValueError(
            "the FRAGO records no base order path; pass base_order (the --base file path)"
        )
    return FRAGO.model_validate(d), ctx.warnings
