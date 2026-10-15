"""Pydantic OPORD -> OpenAIX `opord` (plus the `resources` document that holds its control measures and
channels).

The mapping lives in `_mapping.py`; this module is the public face: `to_openaix`, `OWNED_PATHS` and the
documented authoring-overlay list.

LOSSY / EXTENSION LIST (what lives in `extensions["org.opord-builder.authoring"]`, keyed by dotted model path)
-------------------------------------------------------------------------------------------------------------
Typed in OpenAIX: header (classification, issuing HQ, DTG as date_time, order number, operation name, author,
revision, time zone), print furniture (extension `org.opord-builder.print`), references, task organization (Unit
tree with `parent`, relationships in annex A), mission statement, the area of operations summary, enemy summary and
most-likely / most-dangerous courses of action, higher headquarters (one and two up), assumptions, commander's
intent purpose / key tasks / end state summary, concept of operations summary, scheme summaries, coordinating
instructions (effective time, PIR, FFIR, EEFI, ROE, other), tasks to subordinate units (when every unit is in the
task organization), the signal summary, annex summaries (annex `body`) and the annex status map, authentication and
acknowledgement, control measures (Annex C control_measures and airspace_control, Annex D FSCMs) as
`resources.control_measures`, frequency-table rows as `resources.channels`.

Authoring overlay (no typed OpenAIX home, or a faithful structure would be disproportionate):
  * header.task_organization_note and header.references[].description
  * situation: area_of_interest, terrain, weather, enemy capabilities / recent activities, friendly adjacent and
    other units, interagency, civil considerations, attachments and detachments
  * execution: end-state friendly / enemy / terrain / civil, CONOPS maneuver / decisive / shaping / sustaining /
    reserve / fires, every other scheme, stability, assessment, the coordinating instructions that have no typed
    field (FSCM, ACM, risk, personnel recovery, environmental, themes, CEMA, time line, movement, R&S, orders group,
    rehearsal), and the callsign / purpose / priorities of each subordinate-unit task
  * sustainment (all), command_and_signal except the signal summary, authentication.distribution
  * annexes: title when not canonical, appendices (bodies, frequency-table titles), distribution lists, call-sign
    groups, every typed_body except the measures above (phases, decision points, JPITL, TST, HPT, CAS, CDE, ...)
  * measures: every field the measure document cannot carry (orbit geometry, tanker types, AWACS orbits, AIC
    sectors, radio frequencies of a track, engagement rules, TACAN, ...). Items that no catalogue schema accepts
    (DZ, LZ, PZ, MRR, CFZ, SFA, SAR/SARDOT, AXIS, OTHER, AAR/CAP orbit detail) are extension measures in namespace
    `org.opord-builder.measure` with the original code.
  * kneeboards, openaix (file references) and any value whose reverse conversion is not exact (for example a
    frequency written `251.000`, an upper-case relationship such as `OPCON`).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from opord_builder.openaix import _mapping as mp
from opord_builder.openaix._engine import AUTHORING_NS, PRINT_NS, Ctx, overlay_owned
from opord_builder.openaix.registry import schemas
from opord_builder.openaix.validate import OpenAIXError, validate
from opord_builder.schema.core import OPORD

# JSON pointers (subtree roots) that opord-builder owns in an `opord` document. Everything else in a carried
# document (for example `situation.enemy_forces.units`) is left exactly as carried.
OWNED_PATHS = [
    "/$schema",
    "/kind",
    "/schema_version",
    "/meta",
    "/issuing_headquarters",
    "/date_time",
    "/order_number",
    "/operation_name",
    "/time_zone",
    "/references",
    "/task_organization",
    "/situation",
    "/mission",
    "/execution",
    "/command_and_signal",
    "/annexes",
    "/acknowledgement",
    "/authentication",
    "/resources_ref",
    f"/extensions/{PRINT_NS}",
    f"/extensions/{AUTHORING_NS}",
]
# The same for the `resources` document.
RESOURCES_OWNED_PATHS = [
    "/$schema",
    "/kind",
    "/schema_version",
    "/meta",
    "/resources/control_measures",
    "/resources/channels",
    "/resources/targets",
]
# The same for the `jiptl` document (JPITL entries of Annex D).
JIPTL_OWNED_PATHS = ["/$schema", "/kind", "/schema_version", "/meta", "/targets"]


class OpenAIXExportError(ValueError):
    def __init__(self, errors: list[OpenAIXError]):
        super().__init__(
            "export does not validate against the vendored schema:\n"
            + "\n".join(f"  {e}" for e in errors[:20])
        )
        self.errors = errors


@dataclass
class Bundle:
    opord: dict[str, Any]
    resources: dict[str, Any] | None = None
    jiptl: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)


def _resources_doc(opord: dict, resources: dict) -> dict:
    meta = opord["meta"]
    return {
        "$schema": schemas()["resources"]["$id"],
        "kind": "resources",
        "meta": {
            "id": opord["resources_ref"]["id"],
            "revision": meta["revision"],
            "title": f"Resources of {meta.get('title') or meta['id']}",
        },
        "resources": resources,
        "schema_version": mp.schema_version(),
    }


def _jiptl_doc(opord: dict, targets: list) -> dict:
    meta = opord["meta"]
    return {
        "$schema": schemas()["jiptl"]["$id"],
        "kind": "jiptl",
        "meta": {
            "id": f"{meta['id']}-jiptl",
            "revision": meta["revision"],
            "title": f"JPITL of {meta.get('title') or meta['id']}",
        },
        "schema_version": mp.schema_version(),
        "targets": targets,
    }


def _fresh(model: OPORD) -> Bundle:
    dump = model.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    dump.pop("openaix_source", None)
    ctx = Ctx()
    mp.encode(dump, ctx)
    res = _resources_doc(ctx.doc, ctx.resources) if ctx.resources else None
    jiptl = (
        _jiptl_doc(ctx.doc, ctx.scratch["jiptl"]) if ctx.scratch.get("jiptl") else None
    )
    return Bundle(ctx.doc, res, jiptl, ctx.warnings)


def to_openaix(model: OPORD, *, check: bool = True) -> Bundle:
    """Convert an OPORD to an OpenAIX bundle. When the model carries `openaix_source` (it was imported), only
    the paths in OWNED_PATHS are written over a copy of that original, so typed fields opord-builder lacks
    survive. With `check`, the result is validated and a failure raises OpenAIXExportError."""
    fresh = _fresh(model)
    out = fresh
    carry = model.openaix_source
    if carry:
        from opord_builder.openaix.from_openaix import from_openaix

        old_model, _ = from_openaix(
            carry["opord"],
            carry.get("resources"),
            carry.get("jiptl"),
            carry=False,
            check=False,
        )
        old = _fresh(old_model)
        opord = overlay_owned(carry["opord"], fresh.opord, old.opord, OWNED_PATHS)
        resources = None
        c_res = carry.get("resources")
        if c_res or fresh.resources:
            resources = overlay_owned(
                c_res or {},
                fresh.resources or {},
                old.resources or {},
                RESOURCES_OWNED_PATHS,
            )
            if not c_res and not resources.get("resources"):
                resources = None
        jiptl = None
        c_jp = carry.get("jiptl")
        if c_jp or fresh.jiptl:
            jiptl = overlay_owned(
                c_jp or {}, fresh.jiptl or {}, old.jiptl or {}, JIPTL_OWNED_PATHS
            )
            if not c_jp and not jiptl.get("targets"):
                jiptl = None
        out = Bundle(opord, resources, jiptl, fresh.warnings)
    if check:
        errors = validate(out.opord)
        if out.resources:
            errors += validate(out.resources)
        if out.jiptl:
            errors += validate(out.jiptl)
        if errors:
            raise OpenAIXExportError(errors)
    return Bundle(
        copy.deepcopy(out.opord),
        copy.deepcopy(out.resources),
        copy.deepcopy(out.jiptl),
        out.warnings,
    )
