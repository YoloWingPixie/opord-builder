"""Pure value-level conversions between opord-builder authoring values and OpenAIX values.

No I/O except reading the vendored control-measure catalogue. Every failure raises ConvertError (a ValueError)
and names the offending field. Lossy-but-allowed steps (offset to Z, seconds truncation) append to a
`warnings` list when the caller passes one, else they raise ConvertWarning through `warnings.warn`.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import re
import unicodedata
import warnings as _warnings
from collections.abc import Mapping
from decimal import Decimal
from functools import cache
from typing import Any

from opord_builder.openaix.vendor import coordinates as _coords

MEASURE_NAMESPACE = "org.opord-builder.measure"


class ConvertError(ValueError):
    """A value cannot be converted. `field` names the authoring or OpenAIX field."""

    def __init__(self, field: str, message: str):
        super().__init__(f"{field}: {message}")
        self.field = field


class ConvertWarning(UserWarning):
    pass


def _warn(warnings: list[str] | None, message: str) -> None:
    if warnings is None:
        _warnings.warn(message, ConvertWarning, stacklevel=3)
    else:
        warnings.append(message)


# --------------------------------------------------------------------------- DTG <-> RFC 3339

_UTC = _dt.timezone.utc
MONTHS = (
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
)
_DTG = re.compile(r"(\d{2})(\d{2})(\d{2})Z(" + "|".join(MONTHS) + r")(\d{2})")
_RFC3339 = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(\.\d+)?([Zz]|[+-]\d{2}:\d{2})"
)


def dtg_to_rfc3339(dtg: str, field: str = "dtg") -> str:
    """`181200ZAPR26` -> `2026-04-18T12:00:00Z`. Zulu only; century is 20YY."""
    m = _DTG.fullmatch(dtg.strip()) if isinstance(dtg, str) else None
    if not m:
        raise ConvertError(field, f"not a DTG (DDHHMMZMONYY, Zulu): {dtg!r}")
    day, hour, minute = int(m[1]), int(m[2]), int(m[3])
    try:
        when = _dt.datetime(
            2000 + int(m[5]), MONTHS.index(m[4]) + 1, day, hour, minute, tzinfo=_UTC
        )
    except ValueError as exc:
        raise ConvertError(field, f"invalid date in DTG {dtg!r}: {exc}") from exc
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def rfc3339_to_dtg(
    value: str, field: str = "datetime", warnings: list[str] | None = None
) -> str:
    """RFC 3339 -> DTG. Offsets are converted to Z; seconds are truncated with a warning."""
    m = _RFC3339.fullmatch(value) if isinstance(value, str) else None
    if not m:
        raise ConvertError(field, f"not an RFC 3339 date-time: {value!r}")
    year, month, day, hour, minute, second = (int(m[i]) for i in range(1, 7))
    zone = m[8]
    try:
        when = _dt.datetime(year, month, day, hour, minute, tzinfo=_UTC)
        offset = _dt.timedelta(0)
        if zone not in ("Z", "z"):
            sign = 1 if zone[0] == "+" else -1
            offset = sign * _dt.timedelta(hours=int(zone[1:3]), minutes=int(zone[4:6]))
        when -= offset
    except (ValueError, OverflowError) as exc:
        raise ConvertError(field, f"invalid date-time {value!r}: {exc}") from exc
    if offset:
        _warn(warnings, f"{field}: offset {zone} converted to Z in {value!r}")
    if second or (m[7] and Decimal(m[7])):
        _warn(warnings, f"{field}: seconds truncated from {value!r}")
    if not 2000 <= when.year <= 2099:
        raise ConvertError(
            field, f"year outside 2000-2099, cannot form a DTG: {value!r}"
        )
    return f"{when.day:02d}{when.hour:02d}{when.minute:02d}Z{MONTHS[when.month - 1]}{when.year % 100:02d}"


# --------------------------------------------------------------------------- MGRS <-> GeoPoint

_MGRS_TOKEN = re.compile(
    r"(\d{1,2}[C-HJ-NP-X])\s*([A-HJ-NP-Z][A-HJ-NP-V])\s*(\d+\s+\d+|\d*)(?![0-9A-Za-z])"
)
_NUDGE_M = 0.001  # 1 mm
_DEG_PER_M = 1 / 111_320


def mgrs_digits(text: str) -> int:
    """Total digit count (0-10, even) of a compact MGRS reference."""
    m = re.fullmatch(r"\d{1,2}[A-Z]{3}(\d*)", re.sub(r"\s+", "", text).upper())
    return len(m[1]) if m else 10


def mgrs_to_geopoint(text: str, field: str = "mgrs") -> dict[str, float]:
    """MGRS text -> GeoPoint (south-west corner of the square, 12 decimal places)."""
    try:
        lat, lon = _coords.parse_mgrs(re.sub(r"\s+", "", str(text)).upper())
    except ValueError as exc:
        raise ConvertError(field, str(exc)) from exc
    return {"latitude": round(lat, 12), "longitude": round(lon, 12)}


def _same_point(mgrs: str, lat: float, lon: float) -> bool:
    try:
        plat, plon = _coords.parse_mgrs(mgrs)
    except ValueError:
        return False
    return abs(plat - lat) < 1e-8 and abs(plon - lon) < 1e-8


def geopoint_to_mgrs(
    point: Mapping[str, float],
    digits: int = 10,
    source: str | None = None,
    field: str = "position",
) -> str:
    """GeoPoint -> MGRS with `digits` total digits (default 10 = 1 m). Pass `source` (the text the point came
    from) to take its precision; if float truncation then changes a digit, nudge 1 mm north-east and retry."""
    if source is not None:
        digits = mgrs_digits(source)
    if digits not in (0, 2, 4, 6, 8, 10):
        raise ConvertError(
            field, f"MGRS digits must be 0, 2, 4, 6, 8 or 10, got {digits}"
        )
    lat, lon = point["latitude"], point["longitude"]
    try:
        text = _coords.format_mgrs(lat, lon, digits // 2)
        if source is not None and text != re.sub(r"\s+", "", source).upper():
            lat2 = lat + _NUDGE_M * _DEG_PER_M
            lon2 = lon + _NUDGE_M * _DEG_PER_M / max(math.cos(math.radians(lat)), 1e-9)
            nudged = _coords.format_mgrs(lat2, lon2, digits // 2)
            want = re.sub(r"\s+", "", source).upper()
            if nudged == want:
                text = nudged
            elif _same_point(want, lat, lon):
                # Same position, different label: a square whose corner lies across a zone edge.
                text = want
    except ValueError as exc:
        # A corner just outside the MGRS limits (south of 80S) still names the same point as its source.
        if source is not None and _same_point(
            re.sub(r"\s+", "", source).upper(), lat, lon
        ):
            return re.sub(r"\s+", "", source).upper()
        raise ConvertError(field, str(exc)) from exc
    return text


# --------------------------------------------------------------------------- Geometry

_SEPARATORS = re.compile(r"(?:\s|,|;|->|-|\bto\b|\bthen\b)*", re.IGNORECASE)


def mgrs_tokens(text: str) -> list[str] | None:
    """Compact MGRS tokens if the whole text is nothing but MGRS grids and separators, else None."""
    out: list[str] = []
    pos = 0
    while pos < len(text):
        sep = _SEPARATORS.match(text, pos)
        pos = sep.end()
        if pos >= len(text):
            break
        m = _MGRS_TOKEN.match(text, pos)
        if not m or m.end() == pos:
            return None
        out.append(re.sub(r"\s+", "", m.group(0)))
        pos = m.end()
    return out or None


def to_geometry(
    text: str, area: bool = False, field: str = "grid_or_trace"
) -> dict[str, Any]:
    """Authoring grid text -> Geometry. 1 grid: point. 2+ grids: line, or polygon when `area`.
    Anything that is not purely valid MGRS grids becomes a `description` geometry."""
    if not isinstance(text, str) or not text.strip():
        raise ConvertError(field, "empty geometry text")
    description = {"kind": "description", "text": text.strip()}
    tokens = mgrs_tokens(text)
    if not tokens:
        return description
    try:
        points = [mgrs_to_geopoint(t, field) for t in tokens]
    except ConvertError:
        return description
    if len(points) == 1:
        return {"kind": "point", "position": points[0]}
    if not area:
        return {"kind": "line", "points": points}
    ring = points if points[0] == points[-1] else [*points, points[0]]
    if len({(p["latitude"], p["longitude"]) for p in ring[:-1]}) < 3:
        return description
    return {"kind": "polygon", "rings": [ring]}


def from_geometry(
    geometry: Mapping[str, Any], digits: int = 10, field: str = "geometry"
) -> str:
    """Geometry (point, line, polygon, description) -> authoring text: space-joined MGRS or the description."""
    kind = geometry.get("kind")
    if kind == "description":
        return geometry["text"]
    if kind == "point":
        return geopoint_to_mgrs(geometry["position"], digits, field=field)
    if kind == "line":
        return " ".join(
            geopoint_to_mgrs(p, digits, field=field) for p in geometry["points"]
        )
    if kind == "polygon":
        ring = geometry["rings"][0][:-1]
        return " ".join(geopoint_to_mgrs(p, digits, field=field) for p in ring)
    raise ConvertError(field, f"geometry kind {kind!r} has no authoring text form")


# --------------------------------------------------------------------------- quantities


def _positive(value: Any, field: str) -> float | int:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ConvertError(field, f"not a number: {value!r}")
    if value <= 0:
        raise ConvertError(field, f"must be greater than zero: {value!r}")
    return value


def altitude(
    value: float, unit: str = "ft", reference: str = "MSL", field: str = "altitude"
) -> dict[str, Any]:
    """`*_ft` -> Altitude, unit as authored (no conversion). Flight levels use unit `flight_level`, reference `FL`."""
    if unit not in ("ft", "m", "flight_level"):
        raise ConvertError(field, f"unknown altitude unit {unit!r}")
    if reference not in ("MSL", "AGL", "FL"):
        raise ConvertError(field, f"unknown altitude reference {reference!r}")
    if (reference == "FL") != (unit == "flight_level"):
        raise ConvertError(
            field, "reference FL goes with unit flight_level, and only with it"
        )
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ConvertError(field, f"not a number: {value!r}")
    return {"value": value, "unit": unit, "reference": reference}


def altitude_block(
    floor: float | None,
    ceiling: float | None,
    unit: str = "ft",
    reference: str = "MSL",
    field: str = "altitude",
) -> dict[str, Any]:
    """Floor/ceiling pair -> AltitudeBlock. `None` floor is the surface; `None` ceiling is unlimited."""
    lower = (
        {"surface": True}
        if floor is None
        else altitude(floor, unit, reference, f"{field}.floor")
    )
    upper = (
        {"unlimited": True}
        if ceiling is None
        else altitude(ceiling, unit, reference, f"{field}.ceiling")
    )
    if floor is not None and ceiling is not None and floor > ceiling:
        raise ConvertError(field, f"floor {floor} is above ceiling {ceiling}")
    return {"lower": lower, "upper": upper}


def _quantity_value(obj: Mapping[str, Any], unit: str, field: str) -> float | int:
    if obj.get("unit") != unit:
        raise ConvertError(
            field,
            f"unit is {obj.get('unit')!r}, expected {unit!r}; no unit conversion is done",
        )
    return obj["value"]


def altitude_value(
    alt: Mapping[str, Any], unit: str = "ft", field: str = "altitude"
) -> float | int:
    return _quantity_value(alt, unit, field)


def length(value: float, unit: str = "nm", field: str = "length") -> dict[str, Any]:
    """`*_nm` -> Length, unit as authored."""
    if unit not in ("m", "ft", "nm", "km"):
        raise ConvertError(field, f"unknown length unit {unit!r}")
    return {"value": _positive(value, field), "unit": unit}


def length_value(
    obj: Mapping[str, Any], unit: str = "nm", field: str = "length"
) -> float | int:
    return _quantity_value(obj, unit, field)


def speed(value: float, unit: str = "kt", field: str = "speed") -> dict[str, Any]:
    """`*_kt` -> Speed, unit as authored."""
    if unit not in ("kt", "mach", "km/h"):
        raise ConvertError(field, f"unknown speed unit {unit!r}")
    return {"value": _positive(value, field), "unit": unit}


def speed_value(
    obj: Mapping[str, Any], unit: str = "kt", field: str = "speed"
) -> float | int:
    return _quantity_value(obj, unit, field)


# --------------------------------------------------------------------------- radio

_FREQ = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(MHz)?\s*(AM|FM)?\s*$")
# (band, inclusive low, exclusive high); gaps between bands have no band.
_BANDS = (("hf", 2, 30), ("fm", 30, 88), ("vhf", 108, 174), ("uhf", 225, 400.0000001))


def frequency_band(mhz: float) -> str | None:
    for band, low, high in _BANDS:
        if low <= mhz < high:
            return band
    return None


def parse_frequency(text: str, field: str = "frequency") -> dict[str, Any]:
    """`"251.0 MHz AM"` -> Frequency{value, unit:"MHz", [modulation], [band]}."""
    m = _FREQ.match(text) if isinstance(text, str) else None
    if not m:
        raise ConvertError(
            field,
            f"unparseable frequency {text!r} (expected e.g. '251.000', '124.5 MHz AM')",
        )
    value = float(m[1])
    if value <= 0:
        raise ConvertError(field, f"frequency must be greater than zero: {text!r}")
    out: dict[str, Any] = {"value": value, "unit": "MHz"}
    if m[3]:
        out["modulation"] = m[3]
    band = frequency_band(value)
    if band:
        out["band"] = band
    return out


def format_frequency(freq: Mapping[str, Any], field: str = "frequency") -> str:
    """Frequency -> `"251.0 MHz AM"`. kHz values are converted to MHz exactly."""
    value = Decimal(str(freq["value"]))
    if freq["unit"] == "kHz":
        value = value / 1000
    elif freq["unit"] != "MHz":
        raise ConvertError(field, f"unknown frequency unit {freq['unit']!r}")
    text = format(value.normalize(), "f")
    if "." not in text:
        text += ".0"
    return f"{text} MHz" + (f" {freq['modulation']}" if freq.get("modulation") else "")


_CHANNEL = re.compile(r"^\s*(?:ch(?:annel)?\.?\s*)?(\d+)\s*$", re.IGNORECASE)


def channel_to_preset(text: str, field: str = "channel") -> int:
    """`"Ch 3"`, `"3"`, `"03"` -> 3. Anything else (e.g. `"HF-A"`) is an error."""
    m = _CHANNEL.match(text) if isinstance(text, str) else None
    if not m or int(m[1]) < 1:
        raise ConvertError(field, f"not a numbered radio preset: {text!r}")
    return int(m[1])


def preset_to_channel(preset: int) -> str:
    return f"Ch {preset}"


_TACAN = re.compile(r"^\s*(\d{1,3})\s*([XYxy])\s*$")


def parse_tacan(
    text: str, identifier: str | None = None, field: str = "tacan"
) -> dict[str, Any]:
    """`"11Y"` -> TACAN{channel:11, band:"Y"}."""
    m = _TACAN.match(text) if isinstance(text, str) else None
    if not m or not 1 <= int(m[1]) <= 126:
        raise ConvertError(field, f"not a TACAN channel (1-126 plus X or Y): {text!r}")
    out: dict[str, Any] = {"channel": int(m[1]), "band": m[2].upper()}
    if identifier:
        out["identifier"] = identifier
    return out


def format_tacan(tacan: Mapping[str, Any]) -> str:
    return f"{tacan['channel']}{tacan['band']}"


# --------------------------------------------------------------------------- identifiers


def slug(name: str, taken: set[str] | None = None, field: str = "name") -> str:
    """Name -> Identifier: lowercase, runs of [^a-z0-9] become `-`, `x-` prefix if the first character is not a
    letter. With `taken`, a collision gets `-2`, `-3`, ...; the result is added to `taken`."""
    folded = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")
    if not base:
        raise ConvertError(
            field,
            f"name has no letters or digits to build an identifier from: {name!r}",
        )
    if not base[0].isalpha():
        base = "x-" + base
    result = base
    if taken is not None:
        n = 2
        while result in taken:
            result = f"{base}-{n}"
            n += 1
        taken.add(result)
    return result


def assign_ids(names: list[str], field: str = "name") -> list[str]:
    """Identifiers for the entries of one catalogue, in order, with collision suffixes."""
    taken: set[str] = set()
    return [slug(n, taken, field) for n in names]


class UnresolvedNames(ConvertError):
    def __init__(self, field: str, misses: list[str]):
        super().__init__(
            field,
            f"{len(misses)} name(s) not in the catalogue: "
            + ", ".join(repr(m) for m in misses),
        )
        self.misses = misses


def resolve_names(
    names: list[str], catalogue: Mapping[str, Mapping[str, Any]], field: str = "name"
) -> dict[str, str]:
    """Names -> Identifiers by matching each catalogue entry's `name` exactly. Lists every miss (and ambiguity)."""
    by_name: dict[str, list[str]] = {}
    for ident, entry in catalogue.items():
        by_name.setdefault(entry.get("name"), []).append(ident)
    resolved: dict[str, str] = {}
    misses: list[str] = []
    for name in names:
        ids = by_name.get(name, [])
        if len(ids) == 1:
            resolved[name] = ids[0]
        else:
            misses.append(name if not ids else f"{name} (ambiguous: {', '.join(ids)})")
    if misses:
        raise UnresolvedNames(field, misses)
    return resolved


def names_for_ids(
    ids: list[str], catalogue: Mapping[str, Mapping[str, Any]], field: str = "id"
) -> dict[str, str]:
    """Identifiers -> catalogue `name`. An id with no entry or no name is an error listing every miss."""
    misses = [i for i in ids if i not in catalogue or "name" not in catalogue[i]]
    if misses:
        raise UnresolvedNames(field, misses)
    return {i: catalogue[i]["name"] for i in ids}


# --------------------------------------------------------------------------- enums

# One explicit table per enum: authoring value -> OpenAIX value. Never derived with .lower().
ENUMS: dict[str, dict[str, str]] = {
    "classification": {
        k: k for k in ("UNCLASSIFIED", "CUI", "CONFIDENTIAL", "SECRET", "TOP SECRET")
    },
    "desired_effect": {
        "DESTROY": "destroy",
        "NEUTRALIZE": "neutralize",
        "SUPPRESS": "suppress",
        "DISRUPT": "disrupt",
        "DEGRADE": "degrade",
        "DENY": "deny",
        "DIVERT": "divert",
    },
    "target_timing": {
        "Immediate": "immediate",
        "Planned": "planned",
        "As Acquired": "as_acquired",
    },
    "cas_control_type": {"TYPE_1": "type_1", "TYPE_2": "type_2", "TYPE_3": "type_3"},
    "cas_mark": {
        "LASER": "laser",
        "IR_POINTER": "infrared",
        "SMOKE": "smoke",
        "WP": "white_phosphorus",
        "FLARE": "illumination",
        "NONE": "none",
    },  # GOGGLES has no OpenAIX value
    "coa_designation": {
        "MLCOA": "most_likely",
        "MDCOA": "most_dangerous",
        "COA_3": "other",
        "COA_4": "other",
    },
    "probability": {"high": "high", "medium": "medium", "low": "low"},
    "command_relationship": {
        "OPCON": "operational_control",
        "TACON": "tactical_control",
        "ADCON": "administrative_control",
        "assigned": "assigned",
        "attached": "attached",
        "organic": "organic",
        "DS": "direct_support",
        "GS": "general_support",
        "GSR": "general_support_reinforcing",
        "R": "reinforcing",
    },
    "refueling_method": {},  # TODO(openaix feat/gameplay-fields): BOOM/DROGUE/BOTH have no draft.2 enum
}


def map_enum(enum: str, value: str, field: str | None = None) -> str:
    """Authoring enum value -> OpenAIX value; unknown values raise and list the valid ones."""
    table = ENUMS[enum]
    if value not in table:
        raise ConvertError(
            field or enum,
            f"{value!r} has no OpenAIX {enum} value (valid: {', '.join(table) or 'none'})",
        )
    return table[value]


def unmap_enum(enum: str, value: str, field: str | None = None) -> str:
    """OpenAIX enum value -> authoring value. Where two authoring values share one (COA_3/COA_4), the first wins."""
    for authored, openaix in ENUMS[enum].items():
        if openaix == value:
            return authored
    raise ConvertError(field or enum, f"{value!r} is not an OpenAIX {enum} value")


# --------------------------------------------------------------------------- control measures

# Local aliases in addition to the catalogue's own (HIMEZ, LOMEZ, ROA, SHORADEZ).
_LOCAL_ALIASES = {"SAFE": "SAFES", "RFZ": "RFA", "SAR": "SARDOT"}
# Kinds with no catalogue code that OpenAIX itself validates as measures.
CANONICAL_KINDS = {
    "POINT": "arm",
    "ORBIT": "acm",
    "AIRSPACE": "atcm",
    "AIRWAY": "atcm",
    "NAVAID": "atcm",
}
# No catalogue code at the vendored commit. SFA stays an opord-builder extension permanently (user decision).
# TODO(openaix feat/gameplay-fields): AXIS and CFZ may gain codes; SARDOT is not yet in the catalogue, so SAR falls
# back to an extension measure with code SARDOT until it is (the lookup below prefers the catalogue automatically).
EXTENSION_MEASURES = ("AXIS", "CFZ", "SFA", "SARDOT")


@cache
def _catalogue() -> dict[str, Any]:
    from opord_builder.openaix.registry import VENDOR_DIR

    return json.loads(
        (VENDOR_DIR / "catalogues" / "control-measures.json").read_text(
            encoding="utf-8"
        )
    )


def measure_type(code: str, field: str = "type") -> dict[str, Any]:
    """Authoring measure code -> {code, schema, category, values, alias_of, extension, namespace}.

    Exact-case lookup: catalogue codes, then catalogue aliases, then SAFE, then extension fallback. `values` are
    field values an alias implies (HIMEZ -> {"mez_kind": "high"})."""
    cat = _catalogue()
    types = {t["code"]: t for t in cat["types"]}
    values: dict[str, Any] = {}
    alias_of = None
    resolved = code
    if code in cat["aliases"]:
        alias = cat["aliases"][code]
        resolved, values, alias_of = alias["code"], dict(alias.get("values", {})), code
    elif code in _LOCAL_ALIASES:
        resolved, alias_of = _LOCAL_ALIASES[code], code
    if resolved in types:
        t = types[resolved]
        return {
            "code": resolved,
            "schema": t["schema"],
            "category": t["category"],
            "values": values,
            "alias_of": alias_of,
            "extension": False,
            "namespace": None,
        }
    if code in CANONICAL_KINDS:
        return {
            "code": code,
            "schema": None,
            "category": CANONICAL_KINDS[code],
            "values": {},
            "alias_of": None,
            "extension": False,
            "namespace": None,
        }
    if resolved in EXTENSION_MEASURES:
        return {
            "code": resolved,
            "schema": None,
            "category": None,
            "values": values,
            "alias_of": alias_of,
            "extension": True,
            "namespace": MEASURE_NAMESPACE,
        }
    raise ConvertError(field, f"unknown control measure code {code!r}")
