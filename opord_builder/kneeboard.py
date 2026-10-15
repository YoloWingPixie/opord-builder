"""Kneeboard cards (plain dicts) from an OpenAIX ATO, with hand-authored overrides, rendered to 768x1024 PNG.

`build_cards(ato, resources, flight_id, opord)` returns one card dict per `Flight` plus warnings. A cell whose source
is missing is left blank and gets a warning; no value is ever made up. The optional `opord` supplies the altimeter
setting (`WeatherForecast.altimeter`). The `org.opord-builder.kneeboard` extension (`{"cards": [...]}`) on an
OPORD/FRAGO/ATO or on an ATO flight overrides cards: `merge` lays them over the built cards, explicit values winning
field by field with a warning wherever they disagree with a value the ATO supplied.

A card dict has the shape of `KneeboardCard` in `schemas/extensions/kneeboard.schema.json`.
"""

from __future__ import annotations

import copy
import datetime as _dt
import re
import shutil
import subprocess
import tempfile
import warnings as _warnings
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from opord_builder import load
from opord_builder.format import fmt, forecast_line, humanize, mgrs
from opord_builder.format import frequency as fmt_frequency
from opord_builder.openaix.validate import OpenAIXError, pointer

KG_TO_LB = 2.2046226218
ALL_PHASES = (
    "ALL PHASES"  # radio assignments with no `activities` serve the complete mission
)


# ------------------------------------------------------------------------ resources


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


def fmt_tacan(t: Mapping[str, Any]) -> str:
    """`14Y`; the card shows the channel only, not the identifier `format.tacan` appends."""
    return f"{t['channel']}{t['band']}"


def _freq(channel: Mapping[str, Any]) -> str:
    return fmt_frequency(channel["frequency"])


def _norm(callsign: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", callsign.upper())


def _standard_flight(standard: Mapping[str, Any] | None, callsign: str):
    """The comms-standard flight whose callsign matches (`Ripper 1` matches `RIPPER`), or None."""
    key = re.sub(r"\d+$", "", _norm(callsign))
    return next(
        (
            f
            for f in ((standard or {}).get("flights") or {}).values()
            if _norm(f["callsign"]) == key
        ),
        None,
    )


def _fill(have, std, field, warn, same=lambda have, std: have == std):
    """The ATO value wins. A blank cell takes the standard's value; a different value only warns."""
    if not std:
        return have
    if not have:
        warn(field, "from comms standard")
        return std
    if not same(have, std):
        warn(field, f"{have!r} differs from comms standard {std!r}; ATO value kept")
    return have


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


def _iff_text(ident: Mapping[str, Any], standard, std) -> str:
    """Flight IFF line `M1 20 · M4 ON · M-C ON`: the flight's identification, else the standard's squadron
    mode 1 and IFF defaults. Mode 3 is per position."""
    standard = (
        standard if std else None
    )  # only a flight the standard names takes its values
    defaults = ((standard or {}).get("iff") or {}).get("defaults") or {}
    squadron = ((standard or {}).get("squadrons") or {}).get(std.get("squadron"), {})
    mode1 = ident.get("mode_1") or squadron.get("mode_1") or ""
    mode4 = str(ident.get("mode_4") or defaults.get("mode_4") or "").upper()
    mode_c = defaults.get("mode_c")
    parts = [
        f"M1 {mode1}" if mode1 else "",
        f"M4 {mode4}" if mode4 else "",
        "M-C ON" if mode_c is True else "",
    ]
    return " · ".join(p for p in parts if p)


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


def _forecasts(opord: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    weather = (
        ((opord or {}).get("situation") or {}).get("area_of_operations") or {}
    ).get("weather") or {}
    return weather.get("forecasts") or []


def _covering(
    forecasts: list[Mapping[str, Any]], at: str | None
) -> Mapping[str, Any] | None:
    """The forecast whose window holds `at` (an RFC 3339 time)."""
    for f in forecasts:
        w = f.get("window") or {}
        if (
            at
            and isinstance(w.get("start"), str)
            and isinstance(w.get("end"), str)
            and w["start"] <= at <= w["end"]
        ):
            return f
    return None


def _weather(opord: Mapping[str, Any] | None, at: str | None) -> tuple[str, str | None]:
    """(line, problem): clouds, visibility and surface wind of the forecast that covers the mission."""
    if not opord:
        return "", "no OpenAIX opord given (--opord); left blank"
    forecast = _covering(_forecasts(opord), at)
    line = forecast_line(dict(forecast)) if forecast else ""
    return (
        line,
        None
        if line
        else "no forecast with clouds, visibility or wind covers the takeoff; left blank",
    )


def _steerpoints(
    flight: Mapping[str, Any],
    res: Mapping[str, Any],
    warn,
    period_start: _dt.datetime | None = None,
) -> list[dict[str, str]]:
    """The flight's route as steerpoints: number (RoutePoint.number, else the 1-based position), name, MGRS,
    altitude and action."""
    route = flight.get("route")
    points = (
        ((res.get("routes") or {}).get(route) or {}).get("points") if route else None
    )
    if not points:
        warn(
            "steerpoints",
            f"route {route!r} is not in the resources; left blank"
            if route
            else "flight has no route; left blank",
        )
        return []
    out = []
    for i, p in enumerate(points, 1):
        sp = {
            "number": p.get("number") or i,
            "name": p.get("name") or p.get("id", ""),
            "mgrs": mgrs(p["position"]) if p.get("position") else "",
            "altitude": fmt(p.get("altitude")),
            "action": humanize(p["action"]) if p.get("action") else "",
        }
        time = _timing_text(p.get("timing"), period_start)
        if time:
            sp["time"] = time
        out.append(sp)
    return out


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
    standard: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """One card per Flight (or only `flight_id`). `opord` is an optional OpenAIX opord for the altimeter setting.
    `standard` is an optional OpenAIX comms standard that fills the blank intraflight, TACAN, laser and MIDS cells
    of the flight whose callsign it names. Returns (cards, warnings)."""
    res = dict(resources) if resources is not None else merge_resources(ato, None)
    warnings: list[str] = []
    missions = ato.get("missions") or []
    flights = [(m, f) for m in missions for f in m.get("flights") or []]
    if flight_id is not None:
        flights = [(m, f) for m, f in flights if f["id"] == flight_id]
        if not flights:
            known = ", ".join(f["id"] for m in missions for f in m.get("flights") or [])
            raise ValueError(f"no flight {flight_id!r} in the ATO (flights: {known})")
    cards = [
        _card(ato, m, f, missions, res, opord, warnings, standard) for m, f in flights
    ]
    return cards, warnings


def _card(
    ato: Mapping[str, Any],
    mission: Mapping[str, Any],
    flight: Mapping[str, Any],
    missions: list[Mapping[str, Any]],
    res: Mapping[str, Any],
    opord: Mapping[str, Any] | None,
    warnings: list[str],
    standard: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    callsign = flight["callsign"]
    std = _standard_flight(standard, callsign) or {}
    std_members = {m["member"]: m for m in std.get("members") or []}

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
        laser = _fill(
            laser,
            (std_members.get(n) or {}).get("laser_code", ""),
            f"positions[{n}].laser",
            warn,
        )
        mode3 = (override.get("identification") or {}).get("mode_3") or (
            std_members.get(n) or {}
        ).get("mode_3", "")
        modex = override.get("board_number", "")
        pers = " / ".join(m["name"] for m in override.get("crew") or [])
        missing["modex"] |= not modex
        missing["pers"] |= not pers
        missing["laser"] |= not laser
        position = {"number": n, "modex": modex, "pers": pers, "laser": laser}
        if mode3:
            position["mode3"] = mode3
        positions.append(position)
    if missing["modex"]:
        warn("positions[].modex", "no board_number on a member override; left blank")
    if missing["pers"]:
        warn("positions[].pers", "no crew on a member override; left blank")
    if missing["laser"]:
        warn("positions[].laser", "no laser_code on the member or its SCL; left blank")

    iff = _iff_text(ident, standard, std)

    # tacan: member 1 and flight
    lead_ident = (overrides.get(1) or {}).get("identification") or {}
    lead = lead_ident.get("tacan")
    common = ident.get("tacan")
    pair = std.get("tacan_aa") or {}
    tacan = {
        "lead": _fill(
            fmt_tacan(lead) if lead else "",
            fmt_tacan(pair["lead"]) if pair.get("lead") else "",
            "tacan.lead",
            warn,
        ),
        "flight": _fill(
            fmt_tacan(common) if common else "",
            fmt_tacan(pair["wing"]) if pair.get("wing") else "",
            "tacan.flight",
            warn,
        ),
    }
    if not tacan["lead"]:
        warn("tacan.lead", "member 1 has no identification.tacan; left blank")
    if not tacan["flight"]:
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

    comms = _comms(
        flight, res, [t["channel"] for t in tankers], warn, lead_ident, standard, std
    )
    for t in tankers:
        del t["channel"]

    timing = _timing(ato, mission, res, warn)
    launch = flight.get("launch") or {}
    baro_alt, problem = _altimeter(opord, launch.get("takeoff"))
    if problem:
        warn("baro_alt", problem)
    wx, problem = _weather(opord, launch.get("takeoff"))
    if problem:
        warn("weather", problem)
    steerpoints = _steerpoints(flight, res, warn, _period_start(ato))
    card = {
        "title": callsign,
        "flight_callsign": callsign,
        "msn_number": mission["mission_number"],
        "positions": positions,
        "tacan": tacan,
        "primary_objectives": [objective] if objective else [],
        "weaponeering": (scl or {}).get("name", ""),
        "comms": comms,
        "tankers": tankers,
        "atc": _atc(flight, places, warn),
        "baro_alt": baro_alt,
    }
    if iff:
        card["iff"] = iff
    if wx:
        card["weather"] = wx
    if steerpoints:
        card["steerpoints"] = steerpoints
    if timing:
        card["timing"] = timing
    if fuel_plan:
        card["fuel_plan"] = fuel_plan
    return card


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
                    "tacan": fmt_tacan(tac) if tac else "",
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


def _comms(
    flight, res, tanker_channels, warn, lead_ident, standard=None, std=None
) -> dict[str, Any]:
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
    std = std or {}
    channel = ((standard or {}).get("channels") or {}).get(std.get("intraflight"))
    intra = _fill(intra, _freq(channel) if channel else "", "comms.intra", warn)
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
    # MIDS: the lead's station number and the flight's MIDS voice channel. Only the station can disagree.
    stn = ((std.get("members") or [{}])[0]).get("stn", "")
    voca = std.get("mids_channel")
    want = " ".join(
        p for p in ("Link 16", stn and f"STN {stn}", voca and f"VOCA {voca}") if p
    )
    mids = _fill(
        mids,
        want if stn or voca else "",
        "comms.mids",
        warn,
        same=lambda have, _: not stn or stn in have,
    )
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
                    "frequency": fmt_frequency(f["frequency"]),
                }
            )
        if not place.get("frequencies"):
            warn("atc", f"airfield {pid!r} has no frequencies")
    if not fields:
        warn("atc", "flight has no departure or recovery field; left empty")
    return out


# ------------------------------------------------------------------------ overrides


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


def merge(
    cards: list[dict[str, Any]],
    overrides: list[dict[str, Any]],
    keep_unmatched: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Override cards win field by field, matched to `cards` by flight callsign; warn on disagreement.
    Override cards with no matching card are appended as they are when `keep_unmatched`."""
    warnings: list[str] = []
    by_key: dict[str, dict[str, Any]] = {}
    for o in overrides:
        by_key.setdefault(_norm(o.get("flight_callsign", "")), o)
    used: set[str] = set()
    merged: list[dict[str, Any]] = []
    for card in cards:
        key = _norm(card["flight_callsign"])
        o = by_key.get(key)
        if o is None:
            merged.append(card)
            continue
        used.add(key)
        over = {k: v for k, v in o.items() if k != "flight_callsign"}
        merged.append(_merge(card, over, "", card["flight_callsign"], warnings))
    if keep_unmatched:
        merged += [copy.deepcopy(o) for k, o in by_key.items() if k not in used]
    return merged, warnings


def document_overrides(doc: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The cards of a document's top-level `org.opord-builder.kneeboard` extension."""
    ext = (doc.get("extensions") or {}).get(load.KNEEBOARD) or {}
    return copy.deepcopy(ext.get("cards") or [])


def flight_overrides(ato: Mapping[str, Any], flight_id: str | None = None):
    """Cards from `org.opord-builder.kneeboard` on ATO flights; a card with no `flight_callsign` takes the flight's."""
    out: list[dict[str, Any]] = []
    for m in ato.get("missions") or []:
        for f in m.get("flights") or []:
            if flight_id is not None and f["id"] != flight_id:
                continue
            for card in document_overrides(f):
                card.setdefault("flight_callsign", f["callsign"])
                out.append(card)
    return out


# ------------------------------------------------------------------------ validation


@cache
def _validator() -> Draft202012Validator:
    schema = load.ext_schema("kneeboard")
    return Draft202012Validator(
        {"$ref": "#/$defs/KneeboardCard", "$defs": schema["$defs"]}
    )


def validate_cards(cards: list[dict[str, Any]], base: str = "cards") -> None:
    """Check cards against the kneeboard extension schema. Raises ValueError naming each JSON Pointer."""
    errors = [
        OpenAIXError(pointer((base, i, *e.absolute_path)), e.message)
        for i, card in enumerate(cards)
        for e in _validator().iter_errors(card)
    ]
    if errors:
        lines = "\n".join(f"  {e}" for e in errors[:20])
        raise ValueError(f"invalid kneeboard card:\n{lines}")


# ------------------------------------------------------------------------ files


def _document(path: Path | str, kind: str) -> dict[str, Any]:
    doc = load.load_document(path)
    if doc.get("kind") != kind:
        raise ValueError(
            f"{path}: expected an OpenAIX {kind!r} document, found {doc.get('kind')!r}"
        )
    return doc


def cards_from_files(
    ato_path: Path | str,
    resources_path: Path | str | None = None,
    flight_id: str | None = None,
    opord_path: Path | str | None = None,
    standard_path: Path | str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Load the ATO (and its resources: `resources_path`, else the document its `resources_ref` names), build the
    cards, lay the overrides over them (ATO flights, ATO top level, then the OPORD's top level) and validate the
    result. `standard_path` is an OpenAIX comms standard that fills blank cells. Raises ValueError (DocumentError included) on bad input."""
    ato = _document(ato_path, "ato")
    opord = _document(opord_path, "opord") if opord_path else None
    standard = _document(standard_path, "comms_standard") if standard_path else None
    note = None
    if resources_path:
        res_doc = _document(resources_path, "resources")
        ref = ato.get("resources_ref")
        if ref and (res_doc.get("meta") or {}).get("id") not in (None, ref["id"]):
            note = (
                f"resources document id {res_doc['meta']['id']!r} "
                f"differs from ATO resources_ref {ref['id']!r}"
            )
    else:
        res_doc = load.load_resources(ato, ato_path)
    cards, warnings = build_cards(
        ato, merge_resources(ato, res_doc), flight_id, opord, standard
    )
    if note:
        warnings.insert(0, note)
    overrides = flight_overrides(ato, flight_id) + document_overrides(ato)
    if opord:
        overrides += document_overrides(opord)
    if overrides:
        cards, extra = merge(cards, overrides, keep_unmatched=flight_id is None)
        warnings += extra
    validate_cards(cards)
    return cards, warnings


def cards_from_document(path: Path | str) -> list[dict[str, Any]]:
    """The cards of an OPORD/FRAGO's `org.opord-builder.kneeboard` extension, as authored (no ATO)."""
    cards = document_overrides(load.load_document(path))
    validate_cards(cards)
    return cards


# ------------------------------------------------------------------------ rendering


def render_card_html(card: Mapping[str, Any], index: int = 0) -> str:
    """One card as self-contained HTML sized for 768x1024."""
    from opord_builder import render

    return (
        render.env(True)
        .get_template("kneeboard.html.j2")
        .render(card=card, card_index=index, generated_at=render.stamp())
    )


def render_card_png(
    card: Mapping[str, Any], out_path: Path | str, index: int = 0
) -> Path:
    """One card to a 768x1024 PNG: HTML -> PDF via WeasyPrint, then `pdftoppm` (poppler-utils). Without poppler
    the PDF is kept beside `out_path` instead and its path returned."""
    from weasyprint import HTML

    from opord_builder._paths import TEMPLATES_DIR

    html = render_card_html(card, index)
    out_path = Path(out_path)
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "card.pdf"
        HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf(target=str(pdf_path))
        if shutil.which("pdftoppm"):
            prefix = Path(tmp) / "card"
            subprocess.run(
                [
                    "pdftoppm",
                    "-png",
                    "-r",
                    "96",
                    "-singlefile",
                    str(pdf_path),
                    str(prefix),
                ],
                check=True,
                capture_output=True,
            )
            shutil.move(str(prefix.with_suffix(".png")), str(out_path))
            return out_path
        fallback = out_path.with_suffix(".pdf")
        shutil.move(str(pdf_path), str(fallback))
        _warnings.warn(
            f"pdftoppm not found - wrote PDF instead: {fallback}. "
            "Install poppler-utils for PNG output.",
            stacklevel=2,
        )
        return fallback


def render_cards(
    cards: list[Mapping[str, Any]], out_dir: Path | str, stem: str
) -> list[Path]:
    """Every card to `<stem>_kneeboard_001.png`, ... (DCS sorts kneeboard pages alphanumerically)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return [
        render_card_png(card, out_dir / f"{stem}_kneeboard_{i + 1:03d}.png", i)
        for i, card in enumerate(cards)
    ]
