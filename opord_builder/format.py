"""Small pure formatters: OpenAIX values to the text a reader expects (DTG, MGRS, altitude, frequency, ...)."""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import cache
from typing import Any

from opord_builder.openaix.vendor import coordinates

MONTHS = [
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
]
RFC3339 = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?([Zz]|[+-]\d{2}:\d{2})"
)
SNAKE = re.compile(r"[a-z]+(?:_[a-z]+)+")
CASES = {"case_i": "Case I", "case_ii": "Case II", "case_iii": "Case III"}
VERTICAL = {"surface": "SFC", "unlimited": "UNL"}
NUDGE = 0.001 / 111_320  # 1 mm in degrees: float error must not turn 3200 into 3199
ACRONYMS = frozenset(
    [
        "ccir",
        "pir",
        "hvt",
        "dtg",
        "mgrs",
        "sofa",
        "soi",
        "msr",
        "asr",
        "nfa",
        "cfl",
        "roz",
        "fscm",
        "agm",
        "hptl",
        "moe",
        "mop",
        "uas",
        "isr",
        "pr",
        "cbrn",
        "eod",
        "opsec",
        "fhp",
        "at",
        "ig",
        "km",
        "pa",
        "satcom",
        "axp",
        "ctcp",
        "bsa",
        "bn",
        "bct",
        "hn",
        "lno",
        "coa",
        "mlcoa",
        "mdcoa",
        "nai",
        "tai",
        "ltiov",
        "cal",
        "dal",
        "hns",
        "cmo",
        "cmoc",
        "pace",
        "comsec",
        "nco",
        "ncoic",
        "po",
        "ppc",
        "acm",
        "cema",
        "ffir",
        "eefi",
        "roe",
        "tst",
        "jpitl",
        "cde",
        "tacan",
        "iff",
        "mgrs",
        "aar",
        "cap",
        "awacs",
        "aic",
        "cas",
        "sar",
    ]
)


def number(value: float) -> str:
    return format(Decimal(str(value)).normalize(), "f")


def dtg(value: Any) -> str:
    """RFC 3339 -> `181200ZAPR26` (Zulu); anything else comes back as text."""
    m = RFC3339.fullmatch(value) if isinstance(value, str) else None
    if not m:
        return str(value)
    year, month, day, hour, minute = (int(g) for g in m.groups()[:5])
    when = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    if m[6] not in "Zz":  # an offset: print the Zulu time
        sign = 1 if m[6][0] == "+" else -1
        when -= sign * timedelta(hours=int(m[6][1:3]), minutes=int(m[6][4:6]))
    return f"{when.day:02d}{when.hour:02d}{when.minute:02d}Z{MONTHS[when.month - 1]}{when.year % 100:02d}"


def mgrs(point: dict, digits: int = 10) -> str:
    lat, lon = point["latitude"], point["longitude"]
    lon += NUDGE / max(math.cos(math.radians(lat)), 1e-9)
    return coordinates.format_mgrs(lat + NUDGE, lon, digits // 2)


def altitude(alt: dict) -> str:
    if alt["unit"] == "flight_level":
        return f"FL{int(alt['value']):03d}"
    return f"{number(alt['value'])} {alt['unit']} {alt.get('reference', '')}".strip()


def bearing(b: dict) -> str:
    value = b["value"]
    text = f"{int(value):03d}" if float(value).is_integer() else f"{value:05.1f}"
    return f"{text}° {'M' if b['reference'] == 'magnetic' else 'T'}"


def frequency(freq: dict) -> str:
    """`251.0 MHz AM`; kHz converts to MHz."""
    value = Decimal(str(freq["value"]))
    if freq["unit"] == "kHz":
        value /= 1000
    text = format(value.normalize(), "f")
    text += "" if "." in text else ".0"
    return f"{text} MHz" + (f" {freq['modulation']}" if freq.get("modulation") else "")


def tacan(t: dict) -> str:
    text = f"{t['channel']}{t['band']}"
    return f"{text} ({t['identifier']})" if t.get("identifier") else text


def window(value: Any) -> str:
    if isinstance(value, dict) and "offset_minutes" in value:
        m = value["offset_minutes"]
        return f"T{'+' if m >= 0 else '-'}{number(abs(m))} min"
    return dtg(value)


def fmt(value: Any, names: Any = None) -> str:
    """Text for a scalar or a known OpenAIX shape. `names` maps an identifier to a display name (or is None)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return number(value)
    if isinstance(value, str):
        if RFC3339.fullmatch(value):
            return dtg(value)
        return (
            humanize(value)
            if SNAKE.fullmatch(value)
            else names(value)
            if names
            else value
        )
    if isinstance(value, list):
        return "; ".join(t for t in (fmt(v, names) for v in value) if t)
    keys, unit = set(value), value.get("unit")
    if keys in ({"surface"}, {"unlimited"}):
        return VERTICAL[next(iter(keys))]
    if keys == {"offset_minutes"}:
        return window(value)
    if {"lower", "upper"} <= keys:
        return f"{fmt(value['lower'])} to {fmt(value['upper'])}"
    if unit in ("MHz", "kHz") and "value" in keys:
        return frequency(value)
    if "reference" in keys and unit in ("ft", "m", "flight_level"):
        return altitude(value)
    if keys >= {"value", "reference"} and unit is None:
        return bearing(value)
    if "value" in keys and unit:
        return f"{number(value['value'])} {unit}"
    if {"channel", "band"} <= keys:
        return tacan(value)
    if {"case", "window"} <= keys:
        text = f"{CASES.get(value['case'], value['case'])} {fmt(value['window'])}"
        return text + (f", BRC {bearing(value['brc'])}" if value.get("brc") else "")
    if {"start", "end"} <= keys:
        return f"{window(value['start'])} to {window(value['end'])}"
    if {"latitude", "longitude"} <= keys:
        return mgrs(value)
    if isinstance(value.get("frequency"), dict):
        who = value.get("callsign") or value.get("role") or value.get("name")
        return (
            f"{who} {frequency(value['frequency'])}"
            if who
            else frequency(value["frequency"])
        )
    return "; ".join(
        f"{humanize(k)}: {t}" for k, v in value.items() if (t := fmt(v, names))
    )


SMALL = frozenset(
    [
        "a",
        "an",
        "and",
        "as",
        "at",
        "by",
        "for",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    ]
)


@cache
def humanize(name: str) -> str:
    """`snake_case` -> `Title Case`, keeping acronyms upper case and small words lower case."""
    words = name.replace("_", " ").lower().split()
    return " ".join(
        w.upper() if w in ACRONYMS else w if w in SMALL and i else w.capitalize()
        for i, w in enumerate(words)
    )


@cache
def letter_for(n: int) -> str:
    """1 -> a, 26 -> z, 27 -> aa."""
    out = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        out = chr(97 + r) + out
    return out


def has_content(value: Any) -> bool:
    """True when `value` has any non-empty descendant."""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple)):
        return any(has_content(v) for v in value)
    if isinstance(value, dict):
        return any(has_content(v) for v in value.values())
    return bool(value) if value is not None else False


def paragraphs(text: str) -> list[str]:
    return [
        p.strip()
        for p in re.split(r"\n\s*\n", text.strip().replace("\r\n", "\n"))
        if p.strip()
    ]


COVER = {
    "clear": "CLR",
    "few": "FEW",
    "scattered": "SCT",
    "broken": "BKN",
    "overcast": "OVC",
}
FORECAST_HEAD = {
    "period": "Period", "wind": "Surface Wind", "visibility": "Visibility", "clouds": "Clouds", "ceiling": "Ceiling",
    "temperature": "Temperature", "altimeter": "Altimeter", "precipitation": "Precipitation",
    "winds_aloft": "Winds Aloft", "effects": "Effects",
}  # fmt: skip


def altimeter(p: dict) -> str:
    """`A2992` for inches of mercury, `Q1013` for hectopascals."""
    return (
        f"A{round(p['value'] * 100):04d}"
        if p["unit"] == "inHg"
        else f"Q{round(p['value']):04d}"
    )


def clouds(layers: list[dict]) -> str:
    """`FEW030 BKN080`: coverage and base in hundreds of feet; other units print in full."""
    out = []
    for layer in layers:
        base = layer["base"]
        text = (
            f"{round(base['value'] / 100):03d}"
            if base["unit"] == "ft"
            else f" {fmt(base)}"
        )
        out.append(f"{COVER[layer['coverage']]}{text}")
    return " ".join(out)


def forecast_row(f: dict, note: dict) -> dict[str, str]:
    """The cells of one weather forecast. `note` is the free text the extension keeps for it, printed after a
    typed value (it holds what the typed field could not)."""

    def join(*parts: str) -> str:
        return "; ".join(p for p in parts if p)

    aloft = "; ".join(
        f"{fmt(w['altitude'])} {fmt(w['direction'])} / {fmt(w['speed'])}"
        for w in f.get("winds_aloft") or []
    )
    wind = " / ".join(
        t for t in (fmt(f.get("wind_direction")), fmt(f.get("wind_speed"))) if t
    )
    return {
        "period": " ".join(t for t in (note.get("phase_or_day"), fmt(f.get("window"))) if t),
        "wind": join(wind, note.get("winds", "")),
        "visibility": join(fmt(f.get("visibility")), note.get("visibility", "")),
        "clouds": join(clouds(f.get("clouds") or []), note.get("cloud_cover", "")),
        "ceiling": fmt(f.get("ceiling")),
        "temperature": join(fmt(f.get("temperature")), note.get("temperature_and_humidity", "")),
        "altimeter": altimeter(f["altimeter"]) if f.get("altimeter") else "",
        "precipitation": join(fmt(f.get("precipitation")), note.get("precipitation", "")),
        "winds_aloft": aloft,
        "effects": f.get("effects", ""),
    }  # fmt: skip


def forecast_line(f: dict) -> str:
    """One compact line of a forecast: clouds, visibility and surface wind (typed values only)."""
    row = forecast_row(f, {})
    parts = [("", row["clouds"]), ("VIS ", row["visibility"]), ("WIND ", row["wind"])]
    return " · ".join(f"{label}{text}" for label, text in parts if text)
