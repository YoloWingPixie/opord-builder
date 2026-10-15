"""Build kneeboard cards from an OpenAIX ATO (draft.2 fields only).

`build_cards(ato, resources)` returns one `KneeboardCard` per `Flight` plus a list of
warnings. A cell whose source is missing is left blank and gets a warning; no value is
ever made up. `merge_with_yaml` lays hand-authored YAML cards over the ATO cards
(same flight callsign): explicit YAML values win field by field, with a warning
wherever they disagree with a value the ATO supplied.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from opord_builder.openaix.convert import (
    ConvertError,
    format_frequency,
    format_tacan,
)
from opord_builder.openaix.validate import validate
from opord_builder.schema.shared import KneeboardCard

KG_TO_LB = 2.2046226218
INTRA_PHASE = "ALL PHASES"  # one phase until RadioAssignment.activities exists

BRANCH_NOTE = "not in OpenAIX 0.1.0-draft.2 (feat/gameplay-fields)"


# ------------------------------------------------------------------------ loading


def load_document(path: Path | str, kind: str) -> dict[str, Any]:
    """Read a JSON file, check `kind` and validate it. Raises ValueError listing pointers."""
    path = Path(path)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: not valid JSON: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("kind") != kind:
        found = doc.get("kind") if isinstance(doc, dict) else type(doc).__name__
        raise ValueError(
            f"{path}: expected an OpenAIX {kind!r} document, found {found!r}"
        )
    errors = validate(doc)
    if errors:
        lines = "\n".join(f"  {e}" for e in errors[:20])
        raise ValueError(f"{path}: not a valid OpenAIX {kind} document:\n{lines}")
    return doc


def merge_resources(
    ato: Mapping[str, Any], resources_doc: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Catalogues from the ATO's inline `resources`, overlaid by the resources document."""
    merged: dict[str, Any] = {}
    sources = [ato.get("resources") or {}]
    if resources_doc:
        sources.append(resources_doc.get("resources") or {})
    for src in sources:
        for name, value in src.items():
            if isinstance(value, dict) and isinstance(merged.get(name), dict):
                merged[name] = {**merged[name], **value}
            else:
                merged[name] = value
    return merged


# ------------------------------------------------------------------------ helpers


def _mass_lb(mass: Mapping[str, Any] | None) -> int:
    """Mass -> whole pounds (kg converted). 0 means unknown."""
    if not mass:
        return 0
    value = float(mass["value"])
    return round(value * KG_TO_LB) if mass["unit"] == "kg" else round(value)


def _freq(channel: Mapping[str, Any]) -> str:
    return format_frequency(channel["frequency"])


def _norm(callsign: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", callsign.upper())


def _radio_slot(radio: str | None) -> int | None:
    """COMM1/COMM2 (also 'UHF' -> 1, 'VHF' -> 2)."""
    text = (radio or "").strip().upper()
    if text in ("UHF", "ARC-164"):
        return 1
    if text in ("VHF", "ARC-222"):
        return 2
    m = re.fullmatch(r"(?:COMM?\s*)?([12])", text)
    return int(m[1]) if m else None


def _assignment_text(a: Mapping[str, Any], channels: Mapping[str, Any]) -> str:
    ch = channels[a["channel"]]
    text = _freq(ch)
    if a.get("preset"):
        text += f" (BTN {a['preset']})"
    label = a.get("purpose") or ch.get("name")
    return f"{label}: {text}" if label else text


def _is_intra(a: Mapping[str, Any]) -> bool:
    return "intra" in (a.get("purpose") or "").lower()


# ------------------------------------------------------------------------ building


def build_cards(
    ato: Mapping[str, Any],
    resources: Mapping[str, Any] | None = None,
    flight_id: str | None = None,
) -> tuple[list[KneeboardCard], list[str]]:
    """One card per Flight (or only `flight_id`). Returns (cards, warnings)."""
    res = dict(resources) if resources is not None else merge_resources(ato, None)
    warnings: list[str] = []
    missions = ato.get("missions") or []
    flights = [(m, f) for m in missions for f in m.get("flights") or []]
    if flight_id is not None:
        flights = [(m, f) for m, f in flights if f["id"] == flight_id]
        if not flights:
            known = ", ".join(f["id"] for m in missions for f in m.get("flights") or [])
            raise ValueError(f"no flight {flight_id!r} in the ATO (flights: {known})")
    cards = [_card(m, f, missions, res, warnings) for m, f in flights]
    return cards, warnings


def _card(
    mission: Mapping[str, Any],
    flight: Mapping[str, Any],
    missions: list[Mapping[str, Any]],
    res: Mapping[str, Any],
    warnings: list[str],
) -> KneeboardCard:
    callsign = flight["callsign"]

    def warn(field: str, why: str) -> None:
        warnings.append(f"{callsign}: {field}: {why}")

    channels = res.get("channels") or {}
    scls = res.get("scls") or {}
    places = res.get("places") or {}
    config = flight.get("configuration") or {}
    overrides = {o["member"]: o for o in config.get("member_overrides") or []}
    ident = flight.get("identification") or {}
    tasking = mission.get("tasking") or {}

    # positions: 1..count; laser from the member's SCL (draft.2 has SCL.laser_code)
    positions = []
    lasers_missing = False
    for n in range(1, int(flight["count"]) + 1):
        scl_id = (overrides.get(n) or {}).get("scl") or config.get("primary_scl")
        laser = (scls.get(scl_id) or {}).get("laser_code", "")
        lasers_missing |= not laser
        # TODO(openaix feat/gameplay-fields): board_number -> modex, crew -> pers
        positions.append({"number": n, "modex": "", "pers": "", "laser": laser})
    warn("positions[].modex", f"board_number is {BRANCH_NOTE}; left blank")
    warn("positions[].pers", f"crew is {BRANCH_NOTE}; left blank")
    if lasers_missing:
        warn("positions[].laser", "no laser_code on the SCL; left blank")

    # tacan: member 1 and flight
    lead = (overrides.get(1) or {}).get("identification", {}).get("tacan")
    common = ident.get("tacan")
    tacan = {
        "lead": format_tacan(lead) if lead else "",
        "flight": format_tacan(common) if common else "",
    }
    if not lead:
        warn("tacan.lead", "member 1 has no identification.tacan; left blank")
    if not common:
        warn("tacan.flight", "flight has no identification.tacan; left blank")

    # objectives and weaponeering
    objective = tasking.get("objective")
    if not objective:
        warn("primary_objectives", "mission tasking has no objective; left blank")
    scl = scls.get(config.get("primary_scl"))
    if config.get("primary_scl") and not scl:
        warn(
            "weaponeering",
            f"SCL {config['primary_scl']!r} is not in the resources; left blank",
        )
    elif not config.get("primary_scl"):
        warn("weaponeering", "flight has no configuration; left blank")

    tankers, rcv_tank = _tankers(flight, mission, missions, channels, warn)

    fuel = flight.get("fuel") or {}
    joker, bingo = _mass_lb(fuel.get("joker")), _mass_lb(fuel.get("bingo"))
    # TODO(openaix feat/gameplay-fields): mission_required -> fuel_plan.msn_req_lbs
    warn("fuel_plan.msn_req_lbs", f"mission_required is {BRANCH_NOTE}; left blank")
    if not joker:
        warn("fuel_plan.joker_lbs", "flight fuel has no joker; left blank")
    if not bingo:
        warn("fuel_plan.bingo_lbs", "flight fuel has no bingo; left blank")
    fuel_plan = (
        {
            "msn_req_lbs": 0,
            "joker_lbs": joker,
            "bingo_lbs": bingo,
            "rcv_tank_lbs": rcv_tank,
        }
        if joker or bingo or rcv_tank
        else None
    )

    comms = _comms(flight, channels, [t["channel"] for t in tankers], warn)
    for t in tankers:
        del t["channel"]

    # TODO(openaix feat/gameplay-fields): baro_alt <- WeatherForecast.altimeter
    warn("baro_alt", f"WeatherForecast.altimeter is {BRANCH_NOTE}; left blank")
    return KneeboardCard.model_validate(
        {
            "title": callsign,
            "flight_callsign": callsign,
            "msn_number": mission["mission_number"],
            "positions": positions,
            "tacan": tacan,
            "primary_objectives": [objective] if objective else [],
            "weaponeering": (scl or {}).get("name", ""),
            "fuel_plan": fuel_plan,
            "comms": comms,
            "tankers": tankers,
            "atc": _atc(flight, places, warn),
            "baro_alt": "",
        }
    )


def _tankers(flight, mission, missions, channels, warn):
    """Refueling missions that serve this flight -> (tanker dicts incl. channel id, rcv_tank lb)."""
    support = {
        s["flight"] for s in mission.get("support") or [] if s.get("role") == "tanker"
    }
    out: list[dict[str, Any]] = []
    rcv_total = 0
    buttons = {
        a["channel"]: a.get("preset") for a in flight.get("communications") or []
    }
    for m in missions:
        t = m.get("tasking") or {}
        if t.get("kind") != "refueling":
            continue
        slot = next(
            (r for r in t.get("receivers") or [] if r["flight"] == flight["id"]), None
        )
        served = slot is not None or any(
            f["id"] in support for f in m.get("flights") or []
        )
        if not served:
            continue
        for tf in m.get("flights") or []:
            name = tf["callsign"]
            ch = channels.get(t.get("channel"))
            if not ch:
                warn(
                    f"tankers[{name}].frequency",
                    "tanker mission has no known channel; left blank",
                )
            tac = t.get("tacan") or (tf.get("identification") or {}).get("tacan")
            if not tac:
                warn(
                    f"tankers[{name}].tacan",
                    "no TACAN on the tanker mission or flight; left blank",
                )
            preset = buttons.get(t.get("channel"))
            if not preset:
                warn(
                    f"tankers[{name}].button",
                    "no radio preset for the tanker channel; left blank",
                )
            out.append(
                {
                    "callsign": name,
                    "frequency": _freq(ch) if ch else "",
                    "tacan": format_tacan(tac) if tac else "",
                    "button": f"BTN {preset}" if preset else "",
                    "channel": t.get("channel"),
                }
            )
        if slot:
            rcv_total += _mass_lb(slot.get("planned_offload"))
    if not out:
        warn("tankers", "no Refueling mission serves this flight; left empty")
    elif not rcv_total:
        warn("fuel_plan.rcv_tank_lbs", "no planned_offload for this flight; left blank")
    return out, rcv_total


def _comms(flight, channels, tanker_channels, warn) -> dict[str, Any]:
    assigned = flight.get("communications") or []
    # TODO(openaix feat/gameplay-fields): group by RadioAssignment.activities
    warn(
        "comms.phases", f"RadioAssignment.activities is {BRANCH_NOTE}; one phase shown"
    )
    slots: dict[int, list[str]] = {1: [], 2: []}
    intra = ""
    for a in assigned:
        if a["channel"] not in channels:
            warn("comms", f"channel {a['channel']!r} is not in the resources; skipped")
            continue
        if _is_intra(a):
            intra = intra or _freq(channels[a["channel"]])
            continue
        if a["channel"] in tanker_channels:
            continue  # shown under tankers[]
        slot = _radio_slot(a.get("radio"))
        if slot is None:
            warn(
                "comms.phases", f"radio {a.get('radio')!r} is not COMM1/COMM2; skipped"
            )
            continue
        slots[slot].append(_assignment_text(a, channels))
    if not intra:
        warn("comms.intra", "no radio assignment with purpose 'intra'; left blank")
    ident = flight.get("identification") or {}
    parts = [ident.get("datalink_type"), ident.get("datalink_network")]
    mids = " ".join(p for p in parts if p)
    if mids and ident.get("datalink_station"):
        mids += f" STN {ident['datalink_station']}"
    if not mids:
        # TODO(openaix feat/gameplay-fields): identification.link16
        warn("comms.mids", "no identification.datalink_*; left blank")
    phases = (
        [
            {
                "phase": INTRA_PHASE,
                "comm1": " / ".join(slots[1]),
                "comm2": " / ".join(slots[2]),
            }
        ]
        if slots[1] or slots[2]
        else []
    )
    return {"phases": phases, "intra": intra, "mids": mids}


def _atc(flight, places, warn) -> list[dict[str, str]]:
    fields = []
    launch = flight.get("launch") or {}
    if launch.get("departure"):
        fields.append(launch["departure"])
    dest = (flight.get("recovery") or {}).get("destination")
    if dest and dest not in fields:
        fields.append(dest)
    out = []
    for pid in fields:
        place = places.get(pid)
        if not place:
            warn("atc", f"airfield {pid!r} is not in the resources; no frequencies")
            continue
        label = place.get("ident") or place["name"]
        for f in place.get("frequencies") or []:
            out.append(
                {
                    "name": f"{label} {f['role'].replace('_', ' ').upper()}",
                    "frequency": format_frequency(f["frequency"]),
                }
            )
        if not place.get("frequencies"):
            warn("atc", f"airfield {pid!r} has no frequencies")
    if not fields:
        warn("atc", "flight has no departure or recovery field; left empty")
    return out


# ------------------------------------------------------------------------ YAML merge


def _blank(v: Any) -> bool:
    return v is None or v == "" or v == 0 or v == [] or v == {}


def _merge(base: Any, over: Any, path: str, callsign: str, warnings: list[str]) -> Any:
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = (
                _merge(base[k], v, f"{path}.{k}" if path else k, callsign, warnings)
                if k in base
                else v
            )
        return out
    if (
        isinstance(base, list)
        and isinstance(over, list)
        and all(isinstance(x, dict) and "number" in x for x in base + over)
        and base
    ):
        out = []
        for i in range(max(len(base), len(over))):
            if i >= len(over):
                out.append(base[i])
            elif i >= len(base):
                out.append(over[i])
            else:
                out.append(_merge(base[i], over[i], f"{path}[{i}]", callsign, warnings))
        return out
    if _blank(over):
        return base
    if not _blank(base) and base != over:
        warnings.append(
            f"{callsign}: {path}: YAML value {over!r} overrides ATO value {base!r}"
        )
    return over


def merge_with_yaml(
    ato_cards: list[KneeboardCard],
    yaml_cards: list[KneeboardCard],
    keep_unmatched: bool = True,
) -> tuple[list[KneeboardCard], list[str]]:
    """YAML cards win field by field (explicitly set fields only), warning on disagreement."""
    warnings: list[str] = []
    by_key: dict[str, KneeboardCard] = {}
    for y in yaml_cards:
        by_key.setdefault(_norm(y.flight_callsign), y)
    used: set[str] = set()
    merged: list[KneeboardCard] = []
    for card in ato_cards:
        key = _norm(card.flight_callsign)
        y = by_key.get(key)
        if y is None:
            merged.append(card)
            continue
        used.add(key)
        over = y.model_dump(mode="json", exclude_unset=True)
        over.pop("flight_callsign", None)
        data = _merge(
            card.model_dump(mode="json"), over, "", card.flight_callsign, warnings
        )
        merged.append(KneeboardCard.model_validate(data))
    if keep_unmatched:
        merged += [y for k, y in by_key.items() if k not in used]
    return merged, warnings


def cards_from_files(
    ato_path: Path | str,
    resources_path: Path | str | None = None,
    flight_id: str | None = None,
    yaml_cards: list[KneeboardCard] | None = None,
) -> tuple[list[KneeboardCard], list[str]]:
    """Load, validate, build and (optionally) merge. Raises ValueError on bad input."""
    ato = load_document(ato_path, "ato")
    res_doc = load_document(resources_path, "resources") if resources_path else None
    ref = ato.get("resources_ref")
    if (
        ref
        and res_doc
        and (res_doc.get("meta") or {}).get("id") not in (None, ref["id"])
    ):
        note = f"resources document id {res_doc['meta']['id']!r} differs from ATO resources_ref {ref['id']!r}"
    else:
        note = None
    try:
        cards, warnings = build_cards(ato, merge_resources(ato, res_doc), flight_id)
    except ConvertError as exc:
        raise ValueError(str(exc)) from exc
    if note:
        warnings.insert(0, note)
    if yaml_cards:
        cards, extra = merge_with_yaml(
            cards, yaml_cards, keep_unmatched=flight_id is None
        )
        warnings += extra
    return cards, warnings
