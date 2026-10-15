"""Build kneeboard cards from an OpenAIX ATO (0.2.0-draft.1 gameplay fields included).

`build_cards(ato, resources, flight_id, opord)` returns one `KneeboardCard` per `Flight` plus a list of
warnings. The optional OpenAIX `opord` supplies the altimeter setting (`WeatherForecast.altimeter`). A cell whose source is missing is left blank and gets a warning; no value is
ever made up. `merge_with_yaml` lays hand-authored YAML cards over the ATO cards
(same flight callsign): explicit YAML values win field by field, with a warning
wherever they disagree with a value the ATO supplied.
"""

from __future__ import annotations

import datetime as _dt
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
ALL_PHASES = (
    "ALL PHASES"  # radio assignments with no `activities` serve the complete mission
)


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


def _instant(value: Any, period_start: _dt.datetime | None) -> str | None:
    """A DateTime or an Offset from the ATO period start -> `1030Z`; None when it cannot be resolved."""
    when: _dt.datetime | None = None
    if isinstance(value, str):
        try:
            when = _dt.datetime.fromisoformat(value)
        except ValueError:
            return None
    elif isinstance(value, Mapping) and period_start is not None:
        when = period_start + _dt.timedelta(minutes=value["offset_minutes"])
    if when is None:
        return None
    when = when.astimezone(_dt.timezone.utc)
    return f"{when:%H%M}Z"


def _timing_text(spec: Mapping[str, Any] | None, period_start: _dt.datetime | None):
    """A time condition (at / window / not_after / not_before / on_order) -> kneeboard text, or ''."""
    if not spec:
        return ""
    kind = spec.get("kind")
    if kind == "window":
        start = _instant(spec["window"]["start"], period_start)
        end = _instant(spec["window"]["end"], period_start)
        return f"{start}-{end}" if start and end else ""
    if kind == "on_order":
        return f"ON ORDER: {spec['condition']}"
    at = _instant(spec.get("at"), period_start)
    if not at:
        return ""
    if kind == "not_after":
        return f"NLT {at}"
    if kind == "not_before":
        return f"NET {at}"
    tol = float(spec.get("tolerance_seconds") or 0)
    if not tol:
        return at
    return f"{at} +/-{tol / 60:g} MIN" if tol % 60 == 0 else f"{at} +/-{tol:g} SEC"


def _period_start(ato: Mapping[str, Any]) -> _dt.datetime | None:
    try:
        return _dt.datetime.fromisoformat((ato.get("period") or {})["start"])
    except (KeyError, ValueError):
        return None


def _link16_text(link: Mapping[str, Any]) -> str:
    """Link16 -> `Link 16 STN 01201 FTR 7 MSN 3 SPL 4 TEAM 01202/01203 DONOR 01300`."""
    parts = ["Link 16"]
    if link.get("stn"):
        parts.append(f"STN {link['stn']}")
    for key, tag in (
        ("fighter_channel", "FTR"),
        ("mission_channel", "MSN"),
        ("special_channel", "SPL"),
    ):
        if link.get(key):
            parts.append(f"{tag} {link[key]}")
    for key, tag in (("team", "TEAM"), ("donors", "DONOR")):
        if link.get(key):
            parts.append(f"{tag} {'/'.join(link[key])}")
    return " ".join(parts)


def _altimeter_text(pressure: Mapping[str, Any]) -> str:
    """Pressure -> `29.92 inHg` or `1013 hPa`."""
    if pressure["unit"] == "inHg":
        return f"{pressure['value']:.2f} inHg"
    return f"{pressure['value']:g} hPa"


def _altimeter(
    opord: Mapping[str, Any] | None, at: str | None
) -> tuple[str, str | None]:
    """(setting, problem) from `situation.area_of_operations.weather.forecasts`: the forecast whose window holds
    `at` (an RFC 3339 time) with an altimeter, else the first forecast with one."""
    forecasts = (
        (((opord or {}).get("situation") or {}).get("area_of_operations") or {}).get(
            "weather"
        )
        or {}
    ).get("forecasts") or []
    withset = [f for f in forecasts if f.get("altimeter")]
    if not opord:
        return "", "no OpenAIX opord given (--opord); left blank"
    if not withset:
        return "", "the opord has no WeatherForecast.altimeter; left blank"
    pick = withset[0]
    if at:
        for f in withset:
            w = f.get("window") or {}
            if (
                isinstance(w.get("start"), str)
                and isinstance(w.get("end"), str)
                and w["start"] <= at <= w["end"]
            ):
                pick = f
                break
    return _altimeter_text(pick["altimeter"]), None


# ------------------------------------------------------------------------ building


def build_cards(
    ato: Mapping[str, Any],
    resources: Mapping[str, Any] | None = None,
    flight_id: str | None = None,
    opord: Mapping[str, Any] | None = None,
) -> tuple[list[KneeboardCard], list[str]]:
    """One card per Flight (or only `flight_id`). `opord` is an optional OpenAIX opord for the altimeter setting.
    Returns (cards, warnings)."""
    res = dict(resources) if resources is not None else merge_resources(ato, None)
    warnings: list[str] = []
    missions = ato.get("missions") or []
    flights = [(m, f) for m in missions for f in m.get("flights") or []]
    if flight_id is not None:
        flights = [(m, f) for m, f in flights if f["id"] == flight_id]
        if not flights:
            known = ", ".join(f["id"] for m in missions for f in m.get("flights") or [])
            raise ValueError(f"no flight {flight_id!r} in the ATO (flights: {known})")
    cards = [_card(ato, m, f, missions, res, opord, warnings) for m, f in flights]
    return cards, warnings


def _card(
    ato: Mapping[str, Any],
    mission: Mapping[str, Any],
    flight: Mapping[str, Any],
    missions: list[Mapping[str, Any]],
    res: Mapping[str, Any],
    opord: Mapping[str, Any] | None,
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

    # positions: 1..count. Board number, crew and laser code come from the member's override; the laser code
    # falls back to the member's SCL.
    positions = []
    missing = {"modex": False, "pers": False, "laser": False}
    for n in range(1, int(flight["count"]) + 1):
        override = overrides.get(n) or {}
        scl_id = override.get("scl") or config.get("primary_scl")
        laser = override.get("laser_code") or (scls.get(scl_id) or {}).get(
            "laser_code", ""
        )
        modex = override.get("board_number", "")
        pers = " / ".join(m["name"] for m in override.get("crew") or [])
        missing["modex"] |= not modex
        missing["pers"] |= not pers
        missing["laser"] |= not laser
        positions.append({"number": n, "modex": modex, "pers": pers, "laser": laser})
    if missing["modex"]:
        warn("positions[].modex", "no board_number on a member override; left blank")
    if missing["pers"]:
        warn("positions[].pers", "no crew on a member override; left blank")
    if missing["laser"]:
        warn("positions[].laser", "no laser_code on the member or its SCL; left blank")

    # tacan: member 1 and flight
    lead_ident = (overrides.get(1) or {}).get("identification") or {}
    lead = lead_ident.get("tacan")
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
    msn_req = _mass_lb(fuel.get("mission_required"))
    if not msn_req:
        warn("fuel_plan.msn_req_lbs", "flight fuel has no mission_required; left blank")
    if not joker:
        warn("fuel_plan.joker_lbs", "flight fuel has no joker; left blank")
    if not bingo:
        warn("fuel_plan.bingo_lbs", "flight fuel has no bingo; left blank")
    fuel_plan = (
        {
            "msn_req_lbs": msn_req,
            "joker_lbs": joker,
            "bingo_lbs": bingo,
            "rcv_tank_lbs": rcv_tank,
        }
        if msn_req or joker or bingo or rcv_tank
        else None
    )

    comms = _comms(flight, res, [t["channel"] for t in tankers], warn, lead_ident)
    for t in tankers:
        del t["channel"]

    timing = _timing(ato, mission, res, warn)
    launch = flight.get("launch") or {}
    baro_alt, problem = _altimeter(opord, launch.get("takeoff"))
    if problem:
        warn("baro_alt", problem)
    return KneeboardCard.model_validate(
        {
            "title": callsign,
            "flight_callsign": callsign,
            "msn_number": mission["mission_number"],
            "positions": positions,
            "tacan": tacan,
            "timing": timing,
            "primary_objectives": [objective] if objective else [],
            "weaponeering": (scl or {}).get("name", ""),
            "fuel_plan": fuel_plan,
            "comms": comms,
            "tankers": tankers,
            "atc": _atc(flight, places, warn),
            "baro_alt": baro_alt,
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


def _phase_name(activity_id: str) -> str:
    return re.sub(r"[-_.]+", " ", activity_id).upper()


def _comms(flight, res, tanker_channels, warn, lead_ident) -> dict[str, Any]:
    """Radio assignments grouped into phases by `RadioAssignment.activities` (the flight's own `communications`
    plus its `comm_plan`). An assignment with no activities serves the complete mission (ALL PHASES)."""
    channels = res.get("channels") or {}
    assigned = list(flight.get("communications") or [])
    plan_id = flight.get("comm_plan")
    if plan_id:
        plan = (res.get("comm_plans") or {}).get(plan_id)
        if plan is None:
            warn("comms", f"comm_plan {plan_id!r} is not in the resources; skipped")
        else:
            assigned += plan.get("assignments") or []
    activities = [a["id"] for a in flight.get("activities") or []]
    # phase name -> {1: [...], 2: [...]}; dict order is the phase order shown on the card
    phases: dict[str, dict[int, list[str]]] = {ALL_PHASES: {1: [], 2: []}}
    for aid in activities:
        phases[_phase_name(aid)] = {1: [], 2: []}
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
        names = [ALL_PHASES]
        if a.get("activities"):
            names = []
            for aid in a["activities"]:
                if aid not in activities:
                    warn(
                        "comms.phases",
                        f"activity {aid!r} is not an activity of the flight; skipped",
                    )
                    continue
                names.append(_phase_name(aid))
        for name in names:
            phases[name][slot].append(_assignment_text(a, channels))
    if not intra:
        warn("comms.intra", "no radio assignment with purpose 'intra'; left blank")
    ident = flight.get("identification") or {}
    # Flight-level Link 16 (shared channels) with the lead's own entries laid over it (its station number).
    link = {**(ident.get("link16") or {}), **(lead_ident.get("link16") or {})}
    if link:
        mids = _link16_text(link)
    else:
        parts = [ident.get("datalink_type"), ident.get("datalink_network")]
        mids = " ".join(p for p in parts if p)
        if mids and ident.get("datalink_station"):
            mids += f" STN {ident['datalink_station']}"
    if not mids:
        warn("comms.mids", "no identification.link16 or datalink_*; left blank")
    rows = [
        {
            "phase": name,
            "comm1": " / ".join(radios[1]),
            "comm2": " / ".join(radios[2]),
        }
        for name, radios in phases.items()
        if radios[1] or radios[2]
    ]
    return {"phases": rows, "intra": intra, "mids": mids}


def _timing(ato, mission, res, warn) -> dict[str, str] | None:
    """Package time on target, push time and push point -> KneeboardTiming data, or None when all are blank."""
    package = next(
        (p for p in ato.get("packages") or [] if p["id"] == mission.get("package")),
        None,
    )
    if package is None:
        warn("timing", "mission has no package in the ATO; left blank")
        return None
    start = _period_start(ato)
    tot = _timing_text(package.get("time_on_target"), start)
    push = _timing_text(package.get("push_time"), start)
    point_id = package.get("push_point")
    point = ((res.get("control_measures") or {}).get(point_id) or {}).get("name")
    push_point = point or point_id or ""
    if not tot:
        warn("timing.tot", "package has no time_on_target; left blank")
    if not push:
        warn("timing.push", "package has no push_time; left blank")
    if not (tot or push or push_point):
        return None
    return {"tot": tot, "push": push, "push_point": push_point}


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
    opord_path: Path | str | None = None,
) -> tuple[list[KneeboardCard], list[str]]:
    """Load, validate, build and (optionally) merge. `opord_path` is an OpenAIX opord for the altimeter setting.
    Raises ValueError on bad input."""
    ato = load_document(ato_path, "ato")
    res_doc = load_document(resources_path, "resources") if resources_path else None
    opord = load_document(opord_path, "opord") if opord_path else None
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
        cards, warnings = build_cards(
            ato, merge_resources(ato, res_doc), flight_id, opord
        )
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
