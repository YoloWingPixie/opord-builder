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
