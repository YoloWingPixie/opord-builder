"""Control measures of an OPORD <-> OpenAIX `resources.control_measures`.

Each authoring item (ControlMeasure, FSCM, AirspaceZone, GeoRef, CAPTrack, AARTrack, MinimumRiskRoute) becomes one
measure document chosen by catalogue code (convert.measure_type). A typed document is kept only when the vendored
`control-measure` schema accepts it; otherwise the item becomes an extension measure in namespace
`org.opord-builder.measure` that keeps the code, name, geometry and window. Fields without a typed home stay in the
authoring overlay, and a typed field whose reverse conversion differs from the original is stashed there too.
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from opord_builder.openaix import convert as c
from opord_builder.openaix._engine import AUTHORING_NS, Ctx
from opord_builder.openaix.registry import registry, schemas
from opord_builder.openaix.validate import FORMAT_CHECKER

EXT_TYPE = c.MEASURE_NAMESPACE

# ControlMeasure.type -> catalogue code. "other" has no code and is always an extension measure.
CM_CODES = {
    "axis": "AXIS",
    "phase_line": "PL",
    "objective": "OBJ",
    "boundary": "BOUNDARY",
    "battle_position": "BP",
    "assembly_area": "AA",
    "line_of_departure": "LD",
    "limit_of_advance": "LOA",
    "drop_zone": "DZ",
    "landing_zone": "LZ",
    "pickup_zone": "PZ",
    "named_area_of_interest": "NAI",
    "targeted_area_of_interest": "TAI",
    "checkpoint": "CP",
    "trp": "TRP",
    "other": "OTHER",
}
CM_TYPES = {v: k for k, v in CM_CODES.items()}
CODE_TO_AUTHORING = {
    "SAFES": "SAFE",
    "SARDOT": "SAR",
    "RFA": None,
}  # RFA is also a valid FSCM type itself

# A POINT that stands for an airspace zone kind: the SARDOT of a SAR zone.
POINT_ZONE_ROLE = "search_and_rescue"
POINT_ZONE_CODES = {POINT_ZONE_ROLE: "SARDOT"}

POINT_ROLES = {
    "CP": "control",
    "TRP": "target_reference",
    "BULLSEYE": "bullseye",
    "IP": "initial",
    "EGRESS_PT": "egress",
    "FIX": "fix",
    "WAYPOINT": "fix",
    "ANCHOR": "anchor",
    "NAVAID": "fix",
}
ROLE_TO_GEOREF = {
    "control": "CP",
    "target_reference": "TRP",
    "bullseye": "BULLSEYE",
    "initial": "IP",
    "egress": "EGRESS_PT",
    "fix": "FIX",
    "anchor": "ANCHOR",
}
ROLE_TO_CM = {"control": "CP", "target_reference": "TRP"}

# kind of authoring item -> the pydantic list that holds it (for import)
KIND_LISTS = {
    "control_measure": "control_measures",
    "fscm": "fire_support_coordination_measures",
    "zone": "airspace_zones",
    "geo_ref": "geo_refs",
    "cap": "cap_tracks",
    "aar": "aar_tracks",
    "mrr": "ingress_corridors",
}


def _validator() -> Draft202012Validator:
    return Draft202012Validator(
        schemas()["control-measure"],
        registry=registry(),
        format_checker=FORMAT_CHECKER,
    )


def is_valid(doc: dict[str, Any]) -> bool:
    return not any(True for _ in _validator().iter_errors(doc))


# --------------------------------------------------------------------------- shared field conversions


def _activation(start: str | None, end: str | None) -> dict[str, Any]:
    if start and end:
        return {"start": c.dtg_to_rfc3339(start), "end": c.dtg_to_rfc3339(end)}
    return {"continuous": True}


def _activation_back(active: Any) -> tuple[str | None, str | None]:
    if isinstance(active, dict) and "start" in active and "end" in active:
        try:
            return c.rfc3339_to_dtg(active["start"]), c.rfc3339_to_dtg(active["end"])
        except c.ConvertError:
            return None, None
    return None, None


def _block(floor: Any, ceiling: Any) -> dict[str, Any] | None:
    if floor is None or ceiling is None:
        return None
    try:
        return c.altitude_block(floor, ceiling)
    except c.ConvertError:
        return None


def _block_back(block: Any) -> tuple[Any, Any]:
    try:
        return (
            c.altitude_value(block["lower"]),
            c.altitude_value(block["upper"]),
        )
    except (c.ConvertError, KeyError, TypeError):
        return None, None


def _geometry(text: str | None, area: bool, field: str) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        return c.to_geometry(text, area=area, field=field)
    except c.ConvertError:
        return None


def _geometry_text(geometry: Any) -> str | None:
    if not isinstance(geometry, dict):
        return None
    try:
        return c.from_geometry(geometry)
    except (c.ConvertError, KeyError):
        return None


def _ext_doc(
    code: str, name: str, geometry: dict[str, Any] | None, text: str | None
) -> dict[str, Any]:
    """Extension measure; always valid because a description geometry takes any text."""
    return {
        "name": name,
        "type": EXT_TYPE,
        "geometry": geometry or {"kind": "description", "text": text or name},
        "extensions": {EXT_TYPE: {"code": code}},
    }


# --------------------------------------------------------------------------- per-kind encoders
# Each encoder takes the dumped item and returns (typed_doc | None, code, consumed, ext_geometry_text) where
# `consumed` maps authoring field -> original value for every field the typed doc carries.


def _typed(
    code: str,
    name: str,
    geometry: dict[str, Any] | None,
    active: dict[str, Any],
    extra: dict[str, Any],
) -> dict[str, Any] | None:
    """Build the typed document for catalogue `code`, or None when the code has no typed schema here."""
    try:
        mt = c.measure_type(code)
    except c.ConvertError:
        return None
    if mt["extension"] or geometry is None:
        return None
    schema = (mt["schema"] or "").split(":")[3] if mt["schema"] else ""
    doc: dict[str, Any] = {"name": name, "active": active, **extra}
    if mt["code"] in ("CP", "TRP", "BULLSEYE", "IP") or schema == "point":
        return None  # points are built by _point_doc
    doc["type"] = mt["code"]
    if schema == "measure-volume":
        return None  # a volume needs components, built by the zone encoder
    doc["geometry"] = geometry
    for k, v in mt["values"].items():
        doc[k] = v
    return doc


def _point_doc(
    role: str,
    name: str,
    grid: str | None,
    active: dict[str, Any],
    extra: dict[str, Any],
) -> dict[str, Any]:
    geometry = _geometry(grid, False, "position")
    doc: dict[str, Any] = {
        "name": name,
        "type": "POINT",
        "roles": [role],
        "active": active,
        **extra,
    }
    if geometry and geometry["kind"] == "point":
        doc["position"] = geometry["position"]
    else:
        doc["position_description"] = grid or name
    return doc


def _sardot_point(
    code: str,
    name: str,
    anchor: str | None,
    block: dict[str, Any] | None,
    active: dict[str, Any],
    purpose: str | None,
) -> dict[str, Any] | None:
    """The catalogue's Search and Rescue Point (SARDOT, a POINT with role `search_and_rescue`) for an airspace
    zone of kind SAR, or None when `code` is not SARDOT or the zone has no single anchor point."""
    try:
        if c.measure_type(code)["code"] != "SARDOT" or not anchor:
            return None
    except c.ConvertError:
        return None
    geometry = _geometry(anchor, False, "anchor_point")
    if not geometry or geometry["kind"] != "point":
        return None
    extra: dict[str, Any] = {"description": purpose} if purpose else {}
    if block:
        extra["altitude"] = block
    return _point_doc("search_and_rescue", name, anchor, active, extra)


def _first_valid(
    candidates: list[dict[str, Any] | None], ident: str
) -> dict[str, Any] | None:
    for cand in candidates:
        if cand is None:
            continue
        probe = {**cand, "id": ident}
        if is_valid(probe):
            return cand
    return None


def encode_item(
    kind: str, item: dict[str, Any], ident: str, ctx: Ctx, path: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """(measure document with `id`, consumed {field: original}). Never raises."""
    consumed: dict[str, Any] = {}

    def take(*fields: str) -> list[Any]:
        out = []
        for f in fields:
            out.append(item.get(f))
            if f in item:
                consumed[f] = item[f]
        return out

    doc: dict[str, Any] | None = None
    code = "OTHER"
    name = ""
    text: str | None = None
    geometry: dict[str, Any] | None = None

    if kind == "control_measure":
        name, ctype, grid, eff, term, purpose = take(
            "name",
            "type",
            "grid_or_trace",
            "effective_dtg",
            "termination_dtg",
            "purpose",
        )
        code, text = CM_CODES[ctype], grid
        active = _activation(eff, term)
        extra = {"description": purpose}
        try:
            mt = c.measure_type(code)
        except c.ConvertError:
            mt = None
        area = bool(
            mt and mt["schema"] and mt["schema"].split(":")[3] == "measure-area"
        )
        geometry = _geometry(grid, area, "grid_or_trace")
        if code in ("CP", "TRP"):
            doc = _first_valid(
                [_point_doc(POINT_ROLES[code], name, grid, active, extra)], ident
            )
        else:
            doc = _first_valid([_typed(code, name, geometry, active, extra)], ident)
    elif kind == "fscm":
        ftype, name, start, end, grid, remarks = take(
            "type",
            "name",
            "effective_dtg_start",
            "effective_dtg_end",
            "grid_or_coords",
            "remarks",
        )
        code, text = ftype, grid
        active = _activation(start, end)
        geometry = _geometry(grid, True, "grid_or_coords")
        extra = {"description": remarks} if remarks else {}
        cands = [_typed(code, name, geometry, active, extra)]
        if cands[0] is not None and code in ("RFA", "RFZ") and remarks:
            cands[0]["restrictions"] = [remarks]
        doc = _first_valid(cands, ident)
        if cands[0] is not None and doc is None:
            line = _geometry(grid, False, "grid_or_coords")
            doc = _first_valid([_typed(code, name, line, active, extra)], ident)
    elif kind == "zone":
        name, zkind, anchor, radius, vertices, floor, ceiling, start, end, purpose = (
            take(
                "name",
                "kind",
                "anchor_point",
                "radius_nm",
                "polygon_vertices",
                "altitude_floor_ft",
                "altitude_ceiling_ft",
                "active_dtg_start",
                "active_dtg_end",
                "purpose",
            )
        )
        code, text = zkind, anchor or " ".join(vertices or [])
        active = _activation(start, end)
        comp_geometry: dict[str, Any] | None = None
        if anchor and radius:
            try:
                comp_geometry = {
                    "kind": "circle",
                    "center": c.mgrs_to_geopoint(anchor, "anchor_point"),
                    "radius": c.length(radius, "nm", "radius_nm"),
                }
            except c.ConvertError:
                comp_geometry = None
        elif vertices:
            g = _geometry(" ".join(vertices), True, "polygon_vertices")
            comp_geometry = g if g and g["kind"] == "polygon" else None
        block = _block(floor, ceiling)
        geometry = comp_geometry
        sardot = _sardot_point(code, name, anchor, block, active, purpose)
        if sardot is not None:
            doc = _first_valid([sardot], ident)
            if doc is not None:
                # A search and rescue point has no radius or polygon: those stay in the authoring overlay.
                for f in ("radius_nm", "polygon_vertices"):
                    consumed.pop(f, None)
        elif comp_geometry and block:
            try:
                mt = c.measure_type(code)
            except c.ConvertError:
                mt = None
            if mt and not mt["extension"]:
                cand = {
                    "name": name,
                    "type": mt["code"],
                    "active": active,
                    "description": purpose,
                    "components": [
                        {
                            "id": "c1",
                            "operation": "add",
                            "geometry": comp_geometry,
                            "lower_limit": block["lower"],
                            "upper_limit": block["upper"],
                        }
                    ],
                    **mt["values"],
                }
                doc = _first_valid([cand], ident)
    elif kind == "geo_ref":
        name, gkind, coords, eff, notes = take(
            "name", "kind", "coordinates", "effective_dtg", "notes"
        )
        code, text = gkind, coords
        active = _activation(eff, None)
        extra = {"notes": notes} if notes else {}
        doc = _first_valid(
            [_point_doc(POINT_ROLES[gkind], name, coords, active, extra)], ident
        )
        geometry = _geometry(coords, False, "coordinates")
    elif kind == "cap":
        name, anchor, floor, ceiling = take(
            "name", "anchor_point", "altitude_floor_ft", "altitude_ceiling_ft"
        )
        code, text = "ORBIT", anchor
        geometry = _geometry(anchor, False, "anchor_point")
        block = _block(floor, ceiling)
        if geometry and block:
            doc = _first_valid(
                [
                    {
                        "name": name,
                        "type": "ORBIT",
                        "geometry": geometry,
                        "altitude": block,
                        "active": {"continuous": True},
                    }
                ],
                ident,
            )
    elif kind == "aar":
        name, a1, a2, floor, ceiling, start, end = take(
            "name",
            "anchor_primary",
            "anchor_secondary",
            "altitude_floor_ft",
            "altitude_ceiling_ft",
            "active_dtg_start",
            "active_dtg_end",
        )
        code, text = "ORBIT", " ".join(x for x in (a1, a2) if x)
        geometry = _geometry(text, False, "anchor_primary")
        block = _block(floor, ceiling)
        if geometry and block:
            doc = _first_valid(
                [
                    {
                        "name": name,
                        "type": "ORBIT",
                        "geometry": geometry,
                        "altitude": block,
                        "active": _activation(start, end),
                    }
                ],
                ident,
            )
    elif kind == "mrr":
        name, waypoints, start, end = take(
            "name", "waypoints", "active_dtg_start", "active_dtg_end"
        )
        code, text = "MRR", " ".join(waypoints or [])
        geometry = _geometry(text, False, "waypoints")
        if geometry and geometry["kind"] == "point":
            geometry = None
        # MRR is a corridor in doctrine and needs a width this model does not have: always an extension.
    else:  # pragma: no cover
        raise AssertionError(kind)

    if doc is None:
        try:
            code = c.measure_type(code)[
                "code"
            ]  # RFZ -> RFA, SAR -> SARDOT, SAFE -> SAFES
        except c.ConvertError:
            pass
        doc = _ext_doc(code, name, geometry, text)
        doc["active"] = _activation(*_window_fields(consumed))
    doc = {"id": ident, **doc}
    doc.setdefault("extensions", {})[AUTHORING_NS] = {"item": kind}
    for k in consumed:
        item.pop(k, None)
    return doc, consumed


def _window_fields(consumed: dict[str, Any]) -> tuple[str | None, str | None]:
    start = next(
        (
            consumed[k]
            for k in ("effective_dtg", "effective_dtg_start", "active_dtg_start")
            if k in consumed
        ),
        None,
    )
    end = next(
        (
            consumed[k]
            for k in ("termination_dtg", "effective_dtg_end", "active_dtg_end")
            if k in consumed
        ),
        None,
    )
    return start, end


# --------------------------------------------------------------------------- decoding


def decode_item(doc: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """(kind, partial authoring item) read back from a measure document. Fields the document cannot give are
    absent. `kind` comes from the authoring hint when present, else from the code."""
    hint = (doc.get("extensions") or {}).get(AUTHORING_NS, {}).get("item")
    code = doc.get("type")
    ext_code = None
    if code == EXT_TYPE:
        ext_code = ((doc.get("extensions") or {}).get(EXT_TYPE) or {}).get("code")
    start, end = _activation_back(doc.get("active"))
    name = doc.get("name")
    out: dict[str, Any] = {}
    if name:
        out["name"] = name

    def geom_text(area: bool = False) -> str | None:
        g = doc.get("geometry")
        if g is None and doc.get("position"):
            g = {"kind": "point", "position": doc["position"]}
        if g is None:
            return doc.get("position_description")
        return _geometry_text(g)

    kind = hint
    if kind is None:
        if code == "POINT":
            role = (doc.get("roles") or ["control"])[0]
            kind = (
                "zone"
                if role == POINT_ZONE_ROLE
                else "geo_ref"
                if role in ROLE_TO_GEOREF
                else "control_measure"
            )
        elif code == "ORBIT":
            kind = "cap"
        elif code in (
            "MRR",
            "SAAFR",
            "AIRCOR",
            "AIRRTE",
            "LLTR",
            "TMRR",
            "TC",
            "TR",
            "SC",
            "SL",
        ):
            kind = "mrr"
        elif code in ("MEZ", "ROZ", "HIDACZ", "FEZ", "JEZ", "NFZ", "SAFES", "SAMEZ"):
            kind = "zone"
        elif code in ("CFL", "FSCL", "RFL", "BCL", "NFA", "RFA", "FFA", "ACA", "FSA"):
            kind = "fscm"
        else:
            kind = "control_measure"
    real = ext_code or code

    if kind == "control_measure":
        if code == "POINT":
            real = ROLE_TO_CM.get((doc.get("roles") or ["control"])[0], "CP")
        out["type"] = CM_TYPES.get(real, "other")
        t = geom_text()
        if t:
            out["grid_or_trace"] = t
        if start or end:
            out["effective_dtg"], out["termination_dtg"] = start, end
        if doc.get("description"):
            out["purpose"] = doc["description"]
    elif kind == "fscm":
        out["type"] = real
        t = geom_text()
        if t:
            out["grid_or_coords"] = t
        if start:
            out["effective_dtg_start"] = start
        if end:
            out["effective_dtg_end"] = end
        if doc.get("description"):
            out["remarks"] = doc["description"]
    elif kind == "zone":
        if code == "POINT":  # the catalogue's SARDOT
            real = POINT_ZONE_CODES.get((doc.get("roles") or [""])[0], real)
        out["kind"] = CODE_TO_AUTHORING.get(real) or real
        comps = doc.get("components") or []
        if code == "POINT":
            t = geom_text()
            if t:
                out["anchor_point"] = t
            fl, ce = _block_back(doc.get("altitude"))
            if fl is not None:
                out["altitude_floor_ft"], out["altitude_ceiling_ft"] = fl, ce
        if comps:
            g = comps[0].get("geometry", {})
            if g.get("kind") == "circle":
                out["anchor_point"] = c.geopoint_to_mgrs(g["center"])
                out["radius_nm"] = c.length_value(g["radius"])
            elif g.get("kind") == "polygon":
                out["polygon_vertices"] = _geometry_text(g).split()
            lo, hi = comps[0].get("lower_limit"), comps[0].get("upper_limit")
            fl, ce = _block_back({"lower": lo, "upper": hi})
            if fl is not None:
                out["altitude_floor_ft"], out["altitude_ceiling_ft"] = fl, ce
        if start:
            out["active_dtg_start"] = start
        if end:
            out["active_dtg_end"] = end
        if doc.get("description"):
            out["purpose"] = doc["description"]
    elif kind == "geo_ref":
        out["kind"] = ROLE_TO_GEOREF.get(
            (doc.get("roles") or ["fix"])[0], ext_code or "FIX"
        )
        t = geom_text()
        if t:
            out["coordinates"] = t
        if start and not end:
            pass
        if doc.get("notes"):
            out["notes"] = doc["notes"]
    elif kind in ("cap", "aar"):
        t = geom_text()
        if t:
            if kind == "cap":
                out["anchor_point"] = t
            else:
                parts = t.split()
                out["anchor_primary"] = parts[0]
                if len(parts) > 1:
                    out["anchor_secondary"] = parts[1]
        fl, ce = _block_back(doc.get("altitude"))
        if fl is not None:
            out["altitude_floor_ft"], out["altitude_ceiling_ft"] = fl, ce
        if kind == "aar":
            if start:
                out["active_dtg_start"] = start
            if end:
                out["active_dtg_end"] = end
    elif kind == "mrr":
        t = geom_text()
        if t:
            out["waypoints"] = t.split()
    return kind, out


def _kind_models() -> dict[str, Any]:
    from opord_builder.schema import shared

    return {
        "control_measure": shared.ControlMeasure,
        "fscm": shared.FSCM,
        "zone": shared.AirspaceZone,
        "geo_ref": shared.GeoRef,
        "cap": shared.CAPTrack,
        "aar": shared.AARTrack,
        "mrr": shared.MinimumRiskRoute,
    }


class _Models(dict):
    def __missing__(self, key: str) -> Any:
        self.update(_kind_models())
        return self[key]


KIND_MODELS: dict[str, Any] = _Models()
