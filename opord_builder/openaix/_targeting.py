"""Annex D targeting <-> OpenAIX, at the vendored draft.2.

* `jpitl` -> a `jiptl` document (`JIPTLTarget`: number, rank, name, description, location, component, effect, status,
  engagement means). Category, guidance, CDE, approval authority, no-strike cross-reference, ROE, review DTG and the
  linked HVT rank have no field and stay in the authoring overlay.
* `time_sensitive_targets` -> `annexes.D.targeting.time_sensitive_targets` (id, tst_number, priority) with a mobile
  target in `resources.targets` for the required `target` reference. Everything else stays in the overlay.
* `high_payoff_target_list` + `attack_guidance_matrix` -> `annexes.D.targeting.high_payoff_targets`. An OpenAIX
  HighPayoffTarget needs a priority (the HVT rank) and an effect and timing (the attack guidance row), so the two lists
  are typed together, row for row, only when they have the same length and every effect / timing maps.
  TODO(openaix feat/gameplay-fields): the `jiptl` rename, a category / guidance / CDE field on JIPTLTarget, and an
  HPT effect that does not need the attack guidance matrix.
"""

from __future__ import annotations

from typing import Any

from opord_builder.openaix import convert as c
from opord_builder.openaix._engine import MISSING, get_path

JIPTL_COMPONENTS = {"LAND", "AIR", "MARITIME", "SOF", "CYBER", "SPACE"}
AGM_EFFECTS = {
    "Destroy": "destroy",
    "Neutralize": "neutralize",
    "Suppress": "suppress",
}  # Harass has no value


# --------------------------------------------------------------------------- JPITL


def jpitl_target(item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """(JIPTLTarget, consumed) or None when the entry cannot be typed."""
    consumed: dict[str, Any] = {}
    out: dict[str, Any] = {}

    def take(field: str, key: str | None = None, conv=lambda v: v) -> None:
        if field in item:
            out[key or field] = conv(item[field])
            consumed[field] = item[field]

    take("target_number")
    take("priority_rank")
    take("target_name")
    take("target_description")
    take("desired_effect")
    take("status")
    take("authorized_engagement_means", conv=lambda v: [{"system": s} for s in v])
    if item.get("component_tasked") in JIPTL_COMPONENTS:
        take("component_tasked")
    if "location" in item:
        out["location_mgrs"] = item["location"]
        consumed["location"] = item["location"]
        try:
            out["location"] = c.mgrs_to_geopoint(item["location"], "location")
        except c.ConvertError:
            pass
    if (
        "target_number" not in out
        or "priority_rank" not in out
        or out["priority_rank"] < 1
    ):
        return None
    return out, consumed


def jpitl_item(target: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in (
        "target_number",
        "priority_rank",
        "target_name",
        "target_description",
        "desired_effect",
        "status",
        "component_tasked",
    ):
        if f in target:
            out[f] = target[f]
    if "authorized_engagement_means" in target:
        out["authorized_engagement_means"] = [
            m["system"] for m in target["authorized_engagement_means"]
        ]
    if "location_mgrs" in target:
        out["location"] = target["location_mgrs"]
    elif "location" in target:
        out["location"] = c.geopoint_to_mgrs(target["location"])
    return out


# --------------------------------------------------------------------------- TST


def tst_entry(
    item: dict[str, Any], taken: set[str], target_taken: set[str]
) -> tuple[dict[str, Any], dict[str, Any], str, dict[str, Any]] | None:
    """(TimeSensitiveTarget, resources target, target id, consumed) or None."""
    number = item.get("tst_number")
    cls = item.get("priority_class", "")
    if (
        not number
        or not cls.startswith("TST-")
        or not cls[4:].isdigit()
        or int(cls[4:]) < 1
    ):
        return None
    tid = c.slug(number, target_taken, "targets")
    entry = {
        "id": c.slug(number, taken, "time_sensitive_targets"),
        "tst_number": number,
        "priority": int(cls[4:]),
        "target": tid,
    }
    target: dict[str, Any] = {"name": number, "kind": "mobile", "target_number": number}
    consumed = {"tst_number": number, "priority_class": cls}
    if item.get("target_description"):
        target["description"] = item["target_description"]
        consumed["target_description"] = item["target_description"]
    return entry, target, tid, consumed


def tst_item(entry: dict[str, Any], targets: dict[str, Any]) -> dict[str, Any]:
    out = {"tst_number": entry["tst_number"]}
    if "priority" in entry:
        out["priority_class"] = f"TST-{entry['priority']}"
    t = targets.get(entry.get("target"), {})
    if t.get("description"):
        out["target_description"] = t["description"]
    return out


# --------------------------------------------------------------------------- HPT + attack guidance


def hpt_entries(
    hvts: list[dict], agm: list[dict], taken: set[str], target_taken: set[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    """(HighPayoffTarget list, resources targets). The target reference OpenAIX requires is a mobile target
    named after the HVT description."""
    if not hvts or len(hvts) != len(agm):
        return None
    out, targets = [], {}
    try:
        for h, a in zip(hvts, agm, strict=True):
            tid = c.slug(f"hpt {h['priority_rank']}", target_taken, "targets")
            targets[tid] = {"name": h["target_description"], "kind": "mobile"}
            out.append(
                {
                    "id": c.slug(
                        f"hpt {h['priority_rank']}", taken, "high_payoff_targets"
                    ),
                    "priority": h["priority_rank"],
                    "effect": AGM_EFFECTS[a["effect"]],
                    "timing": c.map_enum("target_timing", a["when"]),
                    "target": tid,
                }
            )
    except (KeyError, c.ConvertError):
        return None
    return out, targets


def hpt_items(
    entries: list[dict[str, Any]], targets: dict[str, Any]
) -> tuple[list[dict], list[dict]]:
    back = {v: k for k, v in AGM_EFFECTS.items()}
    hvts, agm = [], []
    for e in entries:
        hvt: dict[str, Any] = {"priority_rank": e["priority"]}
        t = targets.get(e.get("target"), {})
        if t.get("name"):
            hvt["target_description"] = t["name"]
        hvts.append(hvt)
        row: dict[str, Any] = {}
        if e["effect"] in back:
            row["effect"] = back[e["effect"]]
        if "timing" in e:
            row["when"] = c.unmap_enum("target_timing", e["timing"])
        agm.append(row)
    return hvts, agm


def present(tb: dict, field: str) -> list[dict]:
    v = get_path(tb, field)
    return [] if v is MISSING or not v else v
