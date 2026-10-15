"""Annex D 9-line CAS briefs <-> OpenAIX `CasBrief` (`annexes.D.air_support.cas_briefs`), at 0.2.0-draft.1.

Typed: target description and position, heading and offset side, distance, target elevation, mark (the one
`TargetMark` enum), laser code, friendlies (distance, direction, marking), final attack heading (as a
`final_attack_headings` range), TOT, time to target (seconds), terminal control type, threats (as
`resources.threats`), hazards, danger close and remarks.

Without a typed home, so they stay in the authoring overlay: the IP / BP name (`initial_point` names a control
measure), the egress text (`egress_point` names one), the control agency and CAS callsign (`controller` names an
agency or FAC of the resources), the ground commander's initials, a NONE or GOGGLES mark (`none` is gone from
OpenAIX: the mark is simply absent), and any value that does not fit its typed field (a laser code outside
1111-1788, a marking that is not one of the enumerated words).

A brief needs a position OpenAIX can hold, so a list is typed only when every target location is MGRS.
"""

from __future__ import annotations

import re
from typing import Any

from opord_builder.openaix import convert as c

_LASER = re.compile(r"1[1-7][1-8][1-8]")
THREAT_KIND = (
    "other"  # an authoring threat is free text: it names no OpenAIX threat kind
)
HAZARD_KIND = "other"  # likewise for a hazard


def _bearing(degrees: int) -> dict[str, Any]:
    return {"value": degrees, "reference": "magnetic"}


def cas_brief(
    item: dict[str, Any],
    ident: str,
    threat_ids: dict[str, str],
    threats: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """(CasBrief, consumed {authoring field: original}) or None when the entry has no MGRS target location.
    New threats are added to `threats` (`resources.threats`) and `threat_ids` (name -> identifier)."""
    try:
        position = c.mgrs_to_geopoint(item["target_location"], "target_location")
    except (KeyError, c.ConvertError):
        return None
    out: dict[str, Any] = {"id": ident, "target_position": position}
    consumed: dict[str, Any] = {"target_location": item["target_location"]}

    def take(field: str, key: str, conv=lambda v: v) -> None:
        if item.get(field) is None:
            return
        try:
            out[key] = conv(item[field])
        except (c.ConvertError, KeyError):
            return
        consumed[field] = item[field]

    take("target_description", "target_description")
    take("heading_magnetic", "heading", _bearing)
    take("heading_offset", "offset_direction", lambda v: c.map_enum("cas_offset", v))
    take("distance_nm", "distance", lambda v: c.length(v, "nm", "distance_nm"))
    take(
        "target_elevation_ft",
        "target_elevation",
        lambda v: {"value": v, "reference": "MSL", "unit": "ft"},
    )
    take("mark_type", "mark", lambda v: c.map_enum("cas_mark", v))
    take("laser_code", "laser_code", _laser)
    take(
        "friendlies_distance_m",
        "friendly_distance",
        lambda v: c.length(v, "m", "friendlies_distance_m"),
    )
    take(
        "friendlies_direction",
        "friendly_direction",
        lambda v: c.map_enum("cas_friendly_direction", v),
    )
    take(
        "friendlies_marking",
        "friendly_marking",
        lambda v: c.map_enum("friendly_marking", v.strip().lower()),
    )
    take(
        "final_attack_heading",
        "final_attack_headings",
        lambda v: [{"start_bearing": _bearing(v), "end_bearing": _bearing(v)}],
    )
    take("time_on_target", "time_on_target", c.dtg_to_rfc3339)
    take("time_to_target_min", "time_to_target_seconds", lambda v: v * 60)
    take("type_of_control", "control_type", lambda v: c.map_enum("cas_control_type", v))
    take("danger_close", "danger_close")
    take("remarks", "remarks")
    if item.get("threats"):
        ids = []
        for name in item["threats"]:
            tid = threat_ids.get(name)
            if tid is None:
                tid = threat_ids[name] = c.slug(
                    name, set(threat_ids.values()), "threats"
                )
                threats[tid] = {"name": name, "kind": THREAT_KIND}
            ids.append(tid)
        out["threats"] = ids
        consumed["threats"] = item["threats"]
    if item.get("hazards"):
        out["hazards"] = [
            {"kind": HAZARD_KIND, "description": h} for h in item["hazards"]
        ]
        consumed["hazards"] = item["hazards"]
    return out, consumed


def _laser(code: str) -> str:
    if not _LASER.fullmatch(str(code)):
        raise c.ConvertError("laser_code", f"not a laser code (1111-1788): {code!r}")
    return code


def _whole(value: float) -> Any:
    """A whole number as an int; anything else unchanged, so the authoring model rejects it."""
    return int(value) if float(value).is_integer() else value


def _magnetic(bearing: dict[str, Any]) -> Any:
    if bearing.get("reference") != "magnetic":
        raise c.ConvertError(
            "bearing", "the authoring model holds magnetic bearings only"
        )
    return _whole(bearing["value"])


def cas_item(brief: dict[str, Any], threats: dict[str, Any]) -> dict[str, Any]:
    """Authoring `NineLineCAS` fields read back from a CasBrief; a field with no authoring form is absent."""
    out: dict[str, Any] = {}

    def put(key: str, source: str, conv=lambda v: v) -> None:
        if source not in brief or brief[source] in (None, []):
            return
        try:
            out[key] = conv(brief[source])
        except (c.ConvertError, KeyError, IndexError, TypeError):
            return

    put("target_description", "target_description")
    put("target_location", "target_position", c.geopoint_to_mgrs)
    put("heading_magnetic", "heading", _magnetic)
    put("heading_offset", "offset_direction", lambda v: c.unmap_enum("cas_offset", v))
    put("distance_nm", "distance", lambda v: c.length_value(v, "nm"))
    put(
        "target_elevation_ft",
        "target_elevation",
        lambda v: _whole(c.altitude_value(v, "ft")),
    )
    put("mark_type", "mark", lambda v: c.unmap_enum("cas_mark", v))
    put("laser_code", "laser_code")
    put(
        "friendlies_distance_m",
        "friendly_distance",
        lambda v: _whole(c.length_value(v, "m")),
    )
    put(
        "friendlies_direction",
        "friendly_direction",
        lambda v: c.unmap_enum("cas_friendly_direction", v),
    )
    put(
        "friendlies_marking",
        "friendly_marking",
        lambda v: c.unmap_enum("friendly_marking", v),
    )
    put(
        "final_attack_heading",
        "final_attack_headings",
        lambda v: _magnetic(v[0]["start_bearing"]),
    )
    put(
        "time_on_target",
        "time_on_target",
        lambda v: c.rfc3339_to_dtg(v, warnings=[]),
    )
    put("time_to_target_min", "time_to_target_seconds", lambda v: _whole(v / 60))
    put(
        "type_of_control", "control_type", lambda v: c.unmap_enum("cas_control_type", v)
    )
    put("danger_close", "danger_close")
    put("remarks", "remarks")
    put("threats", "threats", lambda v: [threats.get(t, {}).get("name", t) for t in v])
    put(
        "hazards",
        "hazards",
        lambda v: [h.get("description") or h["kind"].replace("_", " ") for h in v],
    )
    return out
