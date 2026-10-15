"""Migrate SPINS publications and standalone data-source files to native OpenAIX documents, and the bridge back.

SPINS: the publication becomes an OpenAIX `spins` document. Typed OpenAIX fields hold `kind`, `schema_version`, `scope`,
`period`, `base` and the part of `meta` that `Metadata` can type (id, title, revision, operation, issuing_unit, author,
issued_at, classification, distribution). The rest, the publication layout tree, is the top-level extension
`org.opord-builder.spins`: `presentation`, `content`, `changes`, `sidecars` (the old `openaix:` file references) and
`meta` (`handling` and `references`, which `Metadata` cannot type).

Data sources: each file becomes an OpenAIX `resources` document. Every entry is a control measure in
`resources.control_measures` (id = slug of its name). Authoring fields without a typed home, or that do not read back
exactly, sit in the measure's `extensions["org.opord-builder.measure"]["extra"]`. The old document `kind` (cap_tracks,
...) is `table` in the top-level extension `org.opord-builder.resources`, which also keeps the provenance that
`Metadata` cannot hold (`as_of_dtg`, `approved_by`, `notes`). Old `title`, `classification` and `version` are
`meta.title`, `meta.classification` and `meta.revision`; `meta.id` is the file stem.

Variables are not migrated: the old loader substitutes them, and migration starts from the loaded structure.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from opord_builder.load import MEASURE, NS, read
from opord_builder.load import SPINS as SPINS_NS
from opord_builder.migrate import MigrateError, is_native
from opord_builder.openaix import _measures as measures
from opord_builder.openaix._engine import AUTHORING_NS, Ctx
from opord_builder.openaix._mapping import schema_version
from opord_builder.openaix.convert import slug
from opord_builder.renderer import _load_yaml_with_variables
from opord_builder.schema.data_sources import DATA_SOURCE_REGISTRY
from opord_builder.schema.spins import SPINS

RESOURCES_NS = NS + "resources"
TYPED_META = (
    "id",
    "title",
    "revision",
    "operation",
    "issuing_unit",
    "author",
    "issued_at",
    "classification",
    "distribution",
)
EXTRA_META = ("handling", "references")
# data-source kind -> kind of authoring item that `_measures.encode_item` and `decode_item` know
TABLE_ITEMS = {
    "cap_tracks": "cap",
    "aar_tracks": "aar",
    "airspace_zones": "zone",
    "geo_refs": "geo_ref",
    "ingress_corridors": "mrr",
}
# kinds with no measure encoder: the entry becomes a described measure named by this field
NAME_FIELDS = {"awacs_orbits": "callsign", "aic_sectors": "sector_name"}
# old DataSourceMeta -> resources meta, and -> the resources extension
META_TYPED = {
    "title": "title",
    "classification": "classification",
    "version": "revision",
}
META_EXTRA = ("as_of_dtg", "approved_by", "notes")


def _urn(kind: str) -> str:
    return f"urn:openaix:schema:{kind}:{schema_version()}"


# --------------------------------------------------------------------------- SPINS


def migrate_spins(src: Any) -> dict[str, Any]:
    """The native OpenAIX `spins` document for an old SPINS file path, an unprepared `SPINS` model, or old data.
    A native document (or the path of one) comes back unchanged."""
    if isinstance(src, (str, Path)):
        if is_native(src):
            return read(src)
        data, _ = _load_yaml_with_variables(Path(src))
        src = data
    if isinstance(src, dict):
        if src.get("schema_version") == schema_version():
            return src
        src = SPINS.model_validate(src)
    data = src.model_dump(mode="json", exclude_unset=True)
    meta = data["meta"]
    layout: dict[str, Any] = {}
    if extra := {k: meta[k] for k in EXTRA_META if k in meta}:
        layout["meta"] = extra
    for key, name in (("presentation", "presentation"), ("openaix", "sidecars")):
        if key in data:
            layout[name] = data[key]
    for key in ("content", "changes"):
        if key in data:
            layout[key] = data[key]
    doc: dict[str, Any] = {
        "$schema": _urn("spins"),
        "kind": "spins",
        "schema_version": schema_version(),
        "scope": data["scope"],
        "meta": {k: meta[k] for k in TYPED_META if k in meta},
        **{k: data[k] for k in ("period", "base") if k in data},
        "extensions": {SPINS_NS: layout},
    }
    if SPINS.model_validate(legacy_spins_data(doc)) != src:
        raise MigrateError(
            "the native SPINS does not read back to the same publication"
        )
    return doc


def legacy_spins_data(doc: dict[str, Any]) -> dict[str, Any]:
    """The old SPINS data (for `SPINS.model_validate`) of a native `spins` document."""
    layout = (doc.get("extensions") or {}).get(SPINS_NS) or {}
    data: dict[str, Any] = {
        "kind": "spins",
        "schema_version": "0.3",
        "scope": doc.get("scope"),
        "meta": {**(doc.get("meta") or {}), **(layout.get("meta") or {})},
    }
    for key in ("period", "base"):
        if key in doc:
            data[key] = doc[key]
    for old, new in (
        ("presentation", "presentation"),
        ("openaix", "sidecars"),
        ("content", "content"),
        ("changes", "changes"),
    ):
        if new in layout:
            data[old] = layout[new]
    return copy.deepcopy(data)


# --------------------------------------------------------------------------- data sources


def _file_id(path: Path) -> str:
    ident = re.sub(r"[^a-z0-9_.-]+", "-", path.stem.lower()).strip("-")
    return ident if ident[:1].isalpha() else "x-" + ident


def _measure_from_entry(
    table: str, entry: dict[str, Any], ident: str, ctx: Ctx
) -> dict[str, Any]:
    """The control measure for one entry. Whatever the typed document does not carry exactly goes in `extra`."""
    if table in NAME_FIELDS:
        name = entry.pop(NAME_FIELDS[table])
        doc: dict[str, Any] = {
            "id": ident,
            "name": name,
            "type": MEASURE,
            "geometry": {"kind": "description", "text": name},
            "active": {"continuous": True},
        }
        extra = entry
    else:
        item = dict(entry)
        doc, consumed = measures.encode_item(
            TABLE_ITEMS[table], item, ident, ctx, ident
        )
        _, back = measures.decode_item(doc)
        extra = {**item, **{f: v for f, v in consumed.items() if back.get(f) != v}}
        (doc.get("extensions") or {}).pop(AUTHORING_NS, None)
    if extra:
        doc.setdefault("extensions", {}).setdefault(MEASURE, {})["extra"] = extra
    if not doc.get("extensions"):
        doc.pop("extensions", None)
    return doc


def migrate_data_source(src: Any) -> dict[str, Any]:
    """The native OpenAIX `resources` document for an old data-source file (path or loaded data). A native document
    (or the path of one) comes back unchanged."""
    path = None
    if isinstance(src, (str, Path)):
        path = Path(src)
        if is_native(path):
            return read(path)
        src, _ = _load_yaml_with_variables(path)
    if src.get("schema_version") == schema_version():
        return src
    table = src.get("kind")
    model_type = DATA_SOURCE_REGISTRY.get(table)
    if model_type is None:
        raise MigrateError(f"unknown data-source kind {table!r}")
    model = model_type.model_validate(src)
    ctx, ids = Ctx(), set()
    items: dict[str, Any] = {}
    for i, entry in enumerate(model.entries):
        data = entry.model_dump(mode="json", exclude_unset=True)
        ident = slug(data.get(NAME_FIELDS.get(table, "name")) or f"{table}-{i}", ids)
        items[ident] = _measure_from_entry(table, data, ident, ctx)
    old = model.meta.model_dump(mode="json", exclude_unset=True)
    meta = {"id": _file_id(path) if path else table}
    meta.update({new: old[k] for k, new in META_TYPED.items() if k in old})
    doc: dict[str, Any] = {
        "$schema": _urn("resources"),
        "kind": "resources",
        "schema_version": schema_version(),
        "meta": meta,
        "resources": {"control_measures": items},
        "extensions": {
            RESOURCES_NS: {
                "table": table,
                **{k: old[k] for k in META_EXTRA if k in old},
            }
        },
    }
    if legacy_entries(doc) != [
        e.model_dump(mode="json", exclude_unset=True) for e in model.entries
    ]:
        raise MigrateError(
            f"{table}: the native resources do not read back to the same entries"
        )
    return doc


def legacy_data_source(doc: dict[str, Any]) -> dict[str, Any]:
    """The old data-source data (`kind`, `meta`, `entries`) of a native resources document made by migration."""
    ext = (doc.get("extensions") or {}).get(RESOURCES_NS) or {}
    meta = doc.get("meta") or {}
    return {
        "kind": ext.get("table"),
        "meta": {
            **{k: meta[n] for k, n in META_TYPED.items() if n in meta},
            **{k: ext[k] for k in META_EXTRA if k in ext},
        },
        "entries": legacy_entries(doc),
    }


def legacy_entries(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """The authoring entries (dicts) that the control measures of a migrated data-source document stand for."""
    table = ((doc.get("extensions") or {}).get(RESOURCES_NS) or {}).get("table")
    out = []
    for m in (doc.get("resources") or {}).get("control_measures", {}).values():
        extra = copy.deepcopy(
            ((m.get("extensions") or {}).get(MEASURE) or {}).get("extra") or {}
        )
        if table in NAME_FIELDS:
            out.append({NAME_FIELDS[table]: m["name"], **extra})
            continue
        hinted = {
            **m,
            "extensions": {
                **(m.get("extensions") or {}),
                AUTHORING_NS: {"item": TABLE_ITEMS[table]},
            },
        }
        out.append({**measures.decode_item(hinted)[1], **extra})
    return out
