"""One-time migration of authoring YAML to native OpenAIX documents, and the bridge back for the old renderer.

The old converters (`to_openaix`) put whatever OpenAIX cannot type into a flat `authoring` stash keyed by dotted model
path (`annexes.3.typed_body.pace_plans.0.net_name`). Here that stash becomes the nested `org.opord-builder.order`
tree: annexes are keyed by letter, and the extra fields of an item of a typed OpenAIX array are keyed by that item's
identifier. `nest` and `flat` are exact inverses, which the lossless test proves.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

import yaml

from opord_builder.load import (
    KNEEBOARD,
    ORDER,
    PRINT,
    DocumentError,
    load_document,
    read,
    validate_document,
)
from opord_builder.openaix import _measures as measures
from opord_builder.openaix._engine import (
    AUTHORING_NS,
    group_stash,
    sorted_paths,
    ungroup_stash,
)
from opord_builder.openaix._mapping import schema_version
from opord_builder.openaix.convert import slug as c_slug
from opord_builder.openaix.validate import OpenAIXError

CHANNEL_ROW = re.compile(r"\.channels\.\d+$")
TASK_ORG = "header.task_organization"
# top-level keys of the order extension that are not stash entries
SIDE_KEYS = ("document_kind", "base_order_path", "resources_path")
# Fields of an annex that sit beside the stash entries.
STATUS = "status"
# model list (under an annex typed_body) -> where its ids are in the typed OpenAIX annex
AIRSPACE_FIELDS = (
    ("geo_ref", "geo_refs"),
    ("zone", "airspace_zones"),
    ("cap", "cap_tracks"),
    ("aar", "aar_tracks"),
    ("mrr", "ingress_corridors"),
)


class MigrateError(ValueError):
    pass


@dataclass
class Plan:
    """What the typed OpenAIX documents say about the order of the lists the stash indexes."""

    letters: list[str]  # annex letters in model order
    lists: dict[str, list[str]]  # dotted list path -> item identifiers, by index
    unit_path: dict[
        str, str
    ]  # task-organization unit id -> dotted path of its model node


def make_plan(doc: dict, resources: dict | None, letters: list[str]) -> Plan:
    cm = ((resources or {}).get("resources") or {}).get("control_measures") or {}
    lists: dict[str, list[str]] = {}
    ex = doc.get("execution") or {}
    if ex.get("tasks_to_subordinate_units"):
        lists["execution.tasks_to_subordinate_units"] = [
            t["unit"] for t in ex["tasks_to_subordinate_units"]
        ]
    if doc.get("references"):
        lists["header.references"] = [r["id"] for r in doc["references"]]

    def of_kind(ids: list[str], want: str) -> list[str]:
        return [i for i in ids if i in cm and measures.decode_item(cm[i])[0] == want]

    for i, letter in enumerate(letters):
        entry = (doc.get("annexes") or {}).get(letter) or {}
        base = f"annexes.{i}.typed_body"
        if letter == "C":
            lists[f"{base}.control_measures"] = of_kind(
                entry.get("operation_overlay", []), "control_measure"
            )
            ids = (entry.get("airspace") or {}).get("measures", [])
            for kind, field in AIRSPACE_FIELDS:
                lists[f"{base}.airspace_control.{field}"] = of_kind(ids, kind)
        if letter == "D":
            lists[f"{base}.fire_support_coordination_measures"] = of_kind(
                entry.get("fire_support_coordination_measures", []), "fscm"
            )
            lists[f"{base}.cas_nine_lines"] = [
                b["id"] for b in (entry.get("air_support") or {}).get("cas_briefs", [])
            ]
            targeting = entry.get("targeting") or {}
            lists[f"{base}.time_sensitive_targets"] = [
                t["id"] for t in targeting.get("time_sensitive_targets", [])
            ]
            hpt = [t["id"] for t in targeting.get("high_payoff_targets", [])]
            lists[f"{base}.high_payoff_target_list"] = hpt
            lists[f"{base}.attack_guidance_matrix"] = hpt
    lists = {path: ids for path, ids in lists.items() if ids}
    for path, ids in lists.items():
        if len(set(ids)) != len(ids):
            raise MigrateError(
                f"{path}: items share an identifier, cannot key them by it"
            )
    return Plan(letters, lists, _unit_paths(doc.get("task_organization") or {}))


def _unit_paths(units: dict[str, dict]) -> dict[str, str]:
    kids: dict[str | None, list[str]] = {}
    for uid, u in units.items():
        kids.setdefault(u.get("parent"), []).append(uid)
    out: dict[str, str] = {}

    def walk(uid: str, path: str) -> None:
        out[uid] = path
        for j, k in enumerate(kids.get(uid, [])):
            walk(k, f"{path}.subordinate_units.{j}")

    for root in kids.get(None, [])[:1]:
        walk(root, TASK_ORG)
    return out


# --------------------------------------------------------------------------- flat stash <-> nested tree


def _segments(key: str, plan: Plan) -> list[str | int]:
    parts = key.split(".")
    if key.startswith(TASK_ORG + "."):
        path, i = TASK_ORG, 2
        while parts[i : i + 1] == ["subordinate_units"] and parts[i + 1].isdigit():
            path += f".subordinate_units.{parts[i + 1]}"
            i += 2
        uid = next(u for u, p in plan.unit_path.items() if p == path)
        return ["header", "units", uid, *parts[i:]]
    out: list[str | int] = []
    for j, part in enumerate(parts):
        prefix = ".".join(parts[:j])
        if part.isdigit() and prefix == "annexes":
            out.append(plan.letters[int(part)])
        elif part.isdigit() and prefix in plan.lists:
            out.append(plan.lists[prefix][int(part)])
        elif part.isdigit():
            out.append(int(part))
        else:
            out.append("channel_ref" if part == "@channel" else part)
    return out


def _put(tree: dict, segs: list[str | int], value: Any) -> None:
    node: Any = tree
    for seg, nxt in pairwise(segs):
        fresh: Any = [] if isinstance(nxt, int) else {}
        if isinstance(node, list):
            if seg == len(node):
                node.append(fresh)
            node = node[seg]
        else:
            node = node.setdefault(seg, fresh)
    if isinstance(node, list):
        node.append(value)
    else:
        node[segs[-1]] = value


def nest(stash: dict[str, Any], plan: Plan) -> dict[str, Any]:
    tree: dict[str, Any] = {}
    for key in sorted_paths(stash):
        _put(tree, _segments(key, plan), stash[key])
    return tree


def flat(tree: Any, plan: Plan, prefix: str = "") -> dict[str, Any]:
    """The flat stash a nested tree stands for; the inverse of `nest`."""
    out: dict[str, Any] = {}

    def child(path: str, key: str) -> str:
        if path == "annexes":
            key = str(plan.letters.index(key))
        elif path in plan.lists:
            key = str(plan.lists[path].index(key))
        elif key == "channel_ref" and CHANNEL_ROW.search(path):
            key = "@channel"
        return f"{path}.{key}" if path else key

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if path == "header" and k == "units":
                    for uid, fields in v.items():
                        walk(fields, plan.unit_path[uid])
                else:
                    walk(v, child(path, k))
        elif isinstance(node, list) and node and all(isinstance(i, dict) for i in node):
            for i, item in enumerate(node):
                if item:
                    walk(item, f"{path}.{i}")
                else:
                    out[f"{path}.{i}"] = {}
        elif node not in ([], {}):
            out[path] = node

    walk(tree, prefix)
    return out


# --------------------------------------------------------------------------- the order extension


PARAGRAPH_ORDER = (
    "header",
    "situation",
    "execution",
    "sustainment",
    "command_and_signal",
    "annexes",
    "authentication",
    "openaix",
)


def order_extension(
    stash: dict[str, Any], status: dict[str, str], doc: dict, resources: dict | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """(order extension, kneeboard extension or {}) for a flat stash and its annex status map."""
    plan = make_plan(doc, resources, list(status))
    cards = {k: v for k, v in stash.items() if k.split(".")[0] == "kneeboards"}
    rest = {  # the letter of a typed body is the key of its annex
        k: v
        for k, v in stash.items()
        if k not in cards and not k.endswith(".typed_body.letter")
    }
    tree = nest(rest, plan)
    annexes = tree.setdefault("annexes", {})
    for letter, st in status.items():
        annexes[letter] = {STATUS: st, **annexes.get(letter, {})}
    tree["annexes"] = {letter: annexes[letter] for letter in status}
    ext = {k: tree[k] for k in PARAGRAPH_ORDER if k in tree}
    kb = {}
    if cards:
        renamed = {"cards" + k[len("kneeboards") :]: v for k, v in cards.items()}
        kb = {"cards": nest(renamed, plan)["cards"]}
    return ext, kb


def stash_from(
    doc: dict, resources: dict | None
) -> tuple[dict[str, Any], dict[str, str]]:
    """(flat stash, annex status) from the order and kneeboard extensions of a native document."""
    ext = doc.get("extensions") or {}
    x = copy.deepcopy(ext.get(ORDER) or {})
    for k in SIDE_KEYS:
        x.pop(k, None)
    typed = doc.get("annexes") or {}
    letters = [
        *(x.get("annexes") or {}),
        *(a for a in typed if a not in (x.get("annexes") or {})),
    ]
    status = {
        letter: ((x.get("annexes") or {}).get(letter) or {}).get(STATUS, "published")
        for letter in letters
    }
    for a in (x.get("annexes") or {}).values():
        a.pop(STATUS, None)
    plan = make_plan(doc, resources, letters)
    stash = flat(x, plan)
    for i, letter in enumerate(letters):
        if any(k.startswith(f"annexes.{i}.typed_body.") for k in stash):
            stash[f"annexes.{i}.typed_body.letter"] = letter
    cards = (ext.get(KNEEBOARD) or {}).get("cards")
    if cards:
        stash.update(flat({"kneeboards": cards}, plan))
    return stash, status


def legacy_extension(stash: dict[str, Any], status: dict[str, str]) -> dict[str, Any]:
    """The old authoring extension value for a flat stash."""
    return {**group_stash(stash), "@annex_status": status}


def split_authoring(doc: dict) -> tuple[dict[str, Any], dict[str, str]]:
    """(flat stash, annex status) from the old authoring extension of a freshly converted document."""
    flat_stash, special = ungroup_stash(
        doc.get("extensions", {}).get(AUTHORING_NS) or {}
    )
    return flat_stash, special["@annex_status"]


def check_annexes(model: Any) -> Any:
    letters = [a.letter for a in model.annexes]
    if len(set(letters)) != len(letters):
        raise MigrateError(f"annex letters repeat: {letters}")
    return model


# --------------------------------------------------------------------------- reading native files for the old renderer


def is_native(path: Path | str) -> bool:
    """True for an OpenAIX document (as opposed to the old authoring YAML)."""
    try:
        data = read(path)
    except (ValueError, yaml.YAMLError):
        return False
    return isinstance(data, dict) and data.get("schema_version") == schema_version()


def load_resources(doc: dict, path: Path | str) -> dict | None:
    """The resources document an order reaches through `resources_ref`, found by the order extension's
    `resources_path` or else as `resources.{yaml,yml,json}` beside it."""
    ref = doc.get("resources_ref")
    if not ref:
        return None
    here = Path(path).resolve().parent
    named = (doc.get("extensions", {}).get(ORDER) or {}).get("resources_path")
    found = next(
        (
            p
            for p in (
                [here / named]
                if named
                else [here / f"resources.{e}" for e in ("yaml", "yml", "json")]
            )
            if p.is_file()
        ),
        None,
    )
    if found is None:
        raise DocumentError(
            path,
            [
                OpenAIXError(
                    "/resources_ref", f"no resources document for {ref['id']!r}"
                )
            ],
        )
    res = load_document(found)
    meta = res.get("meta", {})
    if (meta.get("id"), meta.get("revision")) != (ref["id"], ref["revision"]):
        raise DocumentError(
            path,
            [
                OpenAIXError(
                    "/resources_ref",
                    f"{found.name} is {meta.get('id')!r} revision {meta.get('revision')!r}",
                )
            ],
        )
    return res


def legacy_opord(doc: dict, resources: dict | None) -> Any:
    """The old authoring model of a native `opord` document."""
    from opord_builder.openaix.from_openaix import from_openaix

    stash, status = stash_from(doc, resources)
    d = copy.deepcopy(doc)
    ext = d.get("extensions") or {}
    d["extensions"] = {
        **({PRINT: ext[PRINT]} if PRINT in ext else {}),
        AUTHORING_NS: legacy_extension(stash, status),
    }
    model, _ = from_openaix(d, resources, None, carry=False, check=False)
    return model


def load_native_opord(path: Path | str) -> Any:
    doc = load_document(path)
    return legacy_opord(doc, load_resources(doc, path))


# --------------------------------------------------------------------------- writing


class _Dumper(yaml.SafeDumper):
    pass


def _str(dumper: yaml.Dumper, data: str) -> yaml.Node:
    block = (
        "\n" in data
        and data.strip("\n") == data.rstrip("\n").lstrip("\n")
        and "\r" not in data
    )
    return dumper.represent_scalar(
        "tag:yaml.org,2002:str", data, style="|" if block else None
    )


_Dumper.add_representer(str, _str)


def dump_yaml(data: Any) -> str:
    text = yaml.dump(
        data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100
    )
    if read_text(text) != data:
        raise MigrateError("YAML round trip changed the data")
    return text


def read_text(text: str) -> Any:
    from opord_builder.load import _Loader

    return yaml.load(text, Loader=_Loader)


def write(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_yaml(data), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- OPORD


def migrate_opord(model: Any, stem: str) -> tuple[dict, dict | None]:
    """(native opord document, resources document or None) for an authoring model."""
    from opord_builder.openaix.to_openaix import to_openaix

    b = to_openaix(check_annexes(model), jiptl=False)
    return native(b.opord, b.resources, stem)


def native(doc: dict, res: dict | None, stem: str) -> tuple[dict, dict | None]:
    """Turn a converted document (old authoring extension) into the native one."""
    stash, status = split_authoring(doc)
    ext = doc["extensions"]
    ext.pop(AUTHORING_NS)
    order, kneeboard = order_extension(stash, status, doc, res)
    if res:
        order = {"resources_path": f"resources/{stem}.yaml", **order}
    ext[ORDER] = order
    if kneeboard:
        ext[KNEEBOARD] = kneeboard
    return doc, res


def checked(path: Path, doc: dict) -> None:
    if errors := validate_document(doc):
        raise DocumentError(path, errors)


# --------------------------------------------------------------------------- FRAGO


def migrate_frago(frago: Any, base: Any, base_path: str, base_stem: str) -> dict:
    """The native frago document for an authoring FRAGO and its base order. `base_path` is written to the
    extension (relative to the FRAGO file); `base_stem` is the file stem the migrated base order uses."""
    from opord_builder.frago import changes_for, order_ref
    from opord_builder.openaix import frago as old
    from opord_builder.openaix._engine import Ctx, flatten
    from opord_builder.openaix.registry import schemas

    base_doc, base_res = migrate_opord(base, base_stem)
    merged, _ = old._overlay_model_dump(base, frago)
    merged_doc, merged_res = migrate_opord(merged, base_stem)
    if any(
        (base_res or {}).get("resources", {}).get(kind, {}).get(i) != v
        for kind, items in (merged_res or {}).get("resources", {}).items()
        for i, v in items.items()
    ):  # a FRAGO may stop using a resource, but it has no resources document of its own
        raise MigrateError(
            "this FRAGO adds or changes control measures or channels, which a frago cannot carry"
        )
    header, _ = old._split(frago)
    header.pop("kind", None)
    ctx = Ctx()
    ctx.doc = {
        "$schema": schemas()["frago"]["$id"],
        "kind": "frago",
        "schema_version": schema_version(),
    }
    for leaf in old._header_leaves():
        leaf.enc(header, ctx)
    left = flatten(header, ctx.typed_lists)
    doc, ref = ctx.doc, order_ref(base_doc)
    number = doc.get("frago_number", "00")
    meta = doc.setdefault("meta", {})
    meta.setdefault("id", old.c.slug(f"{ref['id']} frago {number}"))
    meta.setdefault("revision", "1")
    meta.setdefault(
        "title", f"FRAGO {number} to {base_doc['meta'].get('title') or ref['id']}"
    )
    meta["references"] = [dict(ref)]
    doc["meta"] = dict(sorted(meta.items()))
    doc["base_order"] = ref
    doc["references"] = [dict(ref)]
    if frago.mission:
        doc["mission"] = frago.mission
    doc["changes"] = changes_for(base_doc, merged_doc)
    order = {"base_order_path": left.pop("base_order", base_path), **left}
    assert order["base_order_path"] == base_path, (
        "the FRAGO names another base order than the one loaded"
    )
    doc.setdefault("extensions", {})[ORDER] = order
    return doc


def load_native_frago(
    path: Path | str, base: Path | str | None = None
) -> tuple[Any, Any]:
    """(FRAGO model, base OPORD model) of a native frago document and its base order file."""
    from opord_builder.frago import apply_changes, check_base
    from opord_builder.openaix import frago as old
    from opord_builder.openaix._engine import Ctx
    from opord_builder.schema.core import FRAGO

    path = Path(path)
    doc = load_document(path)
    order = (doc.get("extensions") or {}).get(ORDER) or {}
    base_path = Path(base) if base else path.parent / order["base_order_path"]
    base_doc = load_document(base_path)
    resources = load_resources(base_doc, base_path)
    check_base(doc, base_doc)
    base_model = legacy_opord(base_doc, resources)
    merged = legacy_opord(apply_changes(base_doc, doc["changes"]), resources)
    d: dict[str, Any] = {"kind": "frago", "base_order": order["base_order_path"]}
    for leaf in old._header_leaves():
        leaf.dec(doc, d, Ctx())
    if "previous_fragos" in order:
        d["previous_fragos"] = order["previous_fragos"]
    dump = {"exclude_unset": True, "exclude_none": True, "mode": "json"}
    base_d, merged_d = base_model.model_dump(**dump), merged.model_dump(**dump)
    d.update(old._overlay_from(merged_d, old.sparse_touched(base_d, merged_d)))
    return FRAGO.model_validate(d), base_model


# --------------------------------------------------------------------------- WARNO

WARNO_HEADER = (
    "classification",
    "classification_caveat",
    "copy_number",
    "number_of_copies",
    "issuing_headquarters",
    "place_of_issue",
    "dtg",
    "time_zone",
    "author",
    "operation_name",
    "operation_order_number",
    "logo",
    "page_icon",
    "watermark",
)


def migrate_warno(
    warno: Any, base_path: str | None, stem: str
) -> tuple[dict, dict | None]:
    """(native opord document marked as a WARNO, resources document or None). A WARNO is a sparse order: what it
    leaves out stays out, and its header falls back to the base order when it names one."""
    from opord_builder.openaix import _mapping as mp
    from opord_builder.openaix._engine import Ctx
    from opord_builder.openaix.to_openaix import _resources_doc

    dump = warno.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    side = {
        k: dump.pop(k)
        for k in ("kind", "warno_number", "base_order", "previous_warnos")
        if k in dump
    }
    order_dump = {"header": {k: dump.pop(k) for k in WARNO_HEADER if k in dump}, **dump}
    if "mission" not in order_dump:
        raise MigrateError(
            "a WARNO without a mission cannot be an OpenAIX order, which requires one"
        )
    ctx = Ctx()
    ctx.scratch["no_jiptl"] = True
    mp.encode(order_dump, ctx)
    doc, resources = ctx.doc, ctx.resources
    number = side["warno_number"]
    name = (order_dump["header"].get("operation_name") or "").strip()
    ident = c_slug(f"warno {number} {name}")
    doc["meta"] = dict(
        sorted({**doc["meta"], "id": ident, "title": f"WARNO {number}"}.items())
    )
    if resources:
        doc["resources_ref"]["id"] = f"{ident}-resources"
    res = _resources_doc(doc, resources) if resources else None
    doc, res = native(doc, res, stem)
    order = doc["extensions"][ORDER]
    extra = {"document_kind": "warno", "warno_number": number}
    if side.get("base_order"):
        extra["base_order_path"] = side["base_order"]
    if side.get("previous_warnos"):
        extra["previous_warnos"] = side["previous_warnos"]
    doc["extensions"][ORDER] = {**extra, **order}
    return doc, res


def load_native_warno(path: Path | str) -> tuple[Any, Any]:
    """(WARNO model, base OPORD model or None) of a native opord document marked as a WARNO."""
    from opord_builder.openaix import _mapping as mp
    from opord_builder.openaix._engine import Ctx
    from opord_builder.schema.core import WARNO

    path = Path(path)
    doc = load_document(path)
    order = (doc.get("extensions") or {}).get(ORDER) or {}
    if order.get("document_kind") != "warno":
        raise DocumentError(
            path,
            [
                OpenAIXError(
                    "/extensions/" + ORDER, "not a WARNO: document_kind must be 'warno'"
                )
            ],
        )
    resources = load_resources(doc, path)
    stash, status = stash_from(doc, resources)
    d = copy.deepcopy(doc)
    ext = d.get("extensions") or {}
    d["extensions"] = {
        **({PRINT: ext[PRINT]} if PRINT in ext else {}),
        AUTHORING_NS: legacy_extension(stash, status),
    }
    model = mp.decode(d, resources, Ctx())
    w = {
        "kind": "warno",
        "warno_number": order["warno_number"],
        **model.pop("header", {}),
        **model,
    }
    base = None
    if order.get("base_order_path"):
        w["base_order"] = order["base_order_path"]
        base = load_native_opord(path.parent / order["base_order_path"])
    if "previous_warnos" in order:
        w["previous_warnos"] = order["previous_warnos"]
    return WARNO.model_validate(w), base


# --------------------------------------------------------------------------- files


def legacy_kind(path: Path) -> str:
    """native | opord | frago | warno | spins | data_source, for an authoring file or an OpenAIX document."""
    from opord_builder.renderer import _IncludeLoader

    if is_native(path):
        return "native"
    with path.open(encoding="utf-8") as f:
        data = yaml.load(f, Loader=_IncludeLoader)
    if not isinstance(data, dict):
        raise MigrateError(f"{path}: not an authoring document")
    kind = data.get("kind")
    if kind in ("frago", "warno", "spins"):
        return kind
    if "header" in data:
        return "opord"
    if "entries" in data and kind:
        return "data_source"
    raise MigrateError(f"{path}: not a document opord-builder knows")


def migrate_file(src: Path, out: Path | None = None) -> list[Path]:
    """Migrate one authoring file to a native OpenAIX document; in place unless `out` (a file path) is given.
    Returns the files written. A file that is already native is left as it is (copied when `out` is given)."""
    from opord_builder import renderer

    dest = out or src
    kind = legacy_kind(src)
    if kind == "native":
        if not out or out == src:
            return []
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
        return [dest]
    stem = dest.stem
    written = []
    if kind == "frago":
        frago, base = renderer.load_frago(src)
        doc = migrate_frago(frago, base, frago.base_order, Path(frago.base_order).stem)
        res = None
    elif kind == "warno":
        warno, _ = renderer.load_warno(src)
        doc, res = migrate_warno(warno, warno.base_order, stem)
    elif kind == "opord":
        doc, res = migrate_opord(renderer.load_opord_legacy(src), stem)
    elif kind == "spins":
        from opord_builder.migrate_spins import migrate_spins

        doc, res = migrate_spins(src), None
    else:
        from opord_builder.migrate_spins import migrate_data_source

        doc, res = migrate_data_source(src), None
    for d in (doc, res):
        if d is not None:
            checked(dest, d)
    written.append(write(dest, doc))
    if res is not None:
        written.append(write(dest.parent / "resources" / f"{stem}.yaml", res))
    return written
