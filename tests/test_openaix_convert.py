"""Phase 1: value-level conversions, table driven."""

from __future__ import annotations

import datetime as dt
import json
import random

import pytest
from jsonschema import Draft202012Validator

from opord_builder.openaix import convert as c
from opord_builder.openaix.registry import VENDOR_DIR, registry, schemas
from opord_builder.openaix.validate import FORMAT_CHECKER

COMMON = "urn:openaix:schema:common:0.1.0-draft.2"


def assert_valid(def_name: str, value) -> None:
    """Validate against common.schema.json#/$defs/<def_name>."""
    schema = {"$ref": f"{COMMON}#/$defs/{def_name}"}
    errors = list(
        Draft202012Validator(
            schema, registry=registry(), format_checker=FORMAT_CHECKER
        ).iter_errors(value)
    )
    assert not errors, [e.message for e in errors]


# ---- DTG


@pytest.mark.parametrize(
    ("dtg", "iso"),
    [
        ("181200ZAPR26", "2026-04-18T12:00:00Z"),
        ("010000ZJAN00", "2000-01-01T00:00:00Z"),
        ("312359ZDEC99", "2099-12-31T23:59:00Z"),
        ("290000ZFEB24", "2024-02-29T00:00:00Z"),
    ],
)
def test_dtg_round_trip_table(dtg, iso):
    assert c.dtg_to_rfc3339(dtg) == iso
    assert_valid("DateTime", iso)
    assert c.rfc3339_to_dtg(iso) == dtg


@pytest.mark.parametrize(
    "bad",
    [
        "181200AAPR26",
        "181200ZAPA26",
        "311200ZAPR26",
        "301200ZFEB26",
        "251200ZAPR26 ",
        "",
        "x",
    ],
)
def test_dtg_bad(bad):
    if bad == "251200ZAPR26 ":  # surrounding whitespace is tolerated
        assert c.dtg_to_rfc3339(bad) == "2026-04-25T12:00:00Z"
        return
    with pytest.raises(c.ConvertError, match="dtg"):
        c.dtg_to_rfc3339(bad)


def test_dtg_offset_and_seconds_warn():
    w: list[str] = []
    assert c.rfc3339_to_dtg("2026-04-18T14:00:00+02:00", "start", w) == "181200ZAPR26"
    assert len(w) == 1 and "start" in w[0] and "offset" in w[0]
    w.clear()
    assert c.rfc3339_to_dtg("2026-04-18T12:00:30Z", "start", w) == "181200ZAPR26"
    assert len(w) == 1 and "truncated" in w[0]
    w.clear()
    assert (
        c.rfc3339_to_dtg("2026-04-18T23:30:00-05:00", "start", w) == "190430ZAPR26"
    )  # crosses midnight
    c.rfc3339_to_dtg("2026-04-18T12:00:00Z", "start", w)
    assert len(w) == 1  # exact Z, no seconds: no new warning


def test_dtg_warns_via_warnings_module_without_collector():
    with pytest.warns(c.ConvertWarning):
        c.rfc3339_to_dtg("2026-04-18T12:00:01Z")


@pytest.mark.parametrize(
    "bad",
    [
        "2026-04-18",
        "2026-04-18T12:00:00",
        "2126-04-18T12:00:00Z",
        "1999-04-18T12:00:00Z",
    ],
)
def test_rfc3339_to_dtg_bad(bad):
    with pytest.raises(c.ConvertError):
        c.rfc3339_to_dtg(bad)


def test_dtg_round_trip_1000():
    rng = random.Random(20260418)
    start = dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc)
    span = int(
        (
            dt.datetime(2099, 12, 31, 23, 59, tzinfo=dt.timezone.utc) - start
        ).total_seconds()
        // 60
    )
    for _ in range(1000):
        when = start + dt.timedelta(minutes=rng.randrange(span))
        dtg = f"{when.day:02d}{when.hour:02d}{when.minute:02d}Z{c.MONTHS[when.month - 1]}{when.year % 100:02d}"
        iso = c.dtg_to_rfc3339(dtg)
        assert iso == when.strftime("%Y-%m-%dT%H:%M:00Z")
        assert c.rfc3339_to_dtg(iso) == dtg


# ---- MGRS


def test_mgrs_known_values():
    gp = c.mgrs_to_geopoint("32UMA1500079500")
    assert_valid("GeoPoint", gp)
    assert c.geopoint_to_mgrs(gp) == "32UMA1500079500"
    assert c.geopoint_to_mgrs(gp, 4) == "32UMA1579"
    assert c.mgrs_to_geopoint("32U MA 15000 79500") == gp


@pytest.mark.parametrize(
    ("text", "digits"),
    [
        ("32UMA", 0),
        ("32UMA17", 2),
        ("32UMA1579", 4),
        ("32UMA150795", 6),
        ("32UMA15007950", 8),
        ("32UMA1500079500", 10),
    ],
)
def test_mgrs_source_precision(text, digits):
    assert c.mgrs_digits(text) == digits
    gp = c.mgrs_to_geopoint(text)
    assert c.geopoint_to_mgrs(gp, source=text) == text


@pytest.mark.parametrize(
    "bad", ["", "99UMA1234", "32UMA123", "32UMA12345678901", "hello"]
)
def test_mgrs_bad(bad):
    with pytest.raises(c.ConvertError, match="position"):
        c.mgrs_to_geopoint(bad, "position")


def test_mgrs_digits_validated():
    with pytest.raises(c.ConvertError, match="digits"):
        c.geopoint_to_mgrs({"latitude": 49, "longitude": 11}, 3)


def test_mgrs_round_trip_1000():
    rng = random.Random(4242)
    for _ in range(1000):
        lat, lon = rng.uniform(-79.9, 83.9), rng.uniform(-179.9, 179.9)
        text = _coords_format(lat, lon, rng.choice([0, 1, 2, 3, 4, 5]))
        gp = c.mgrs_to_geopoint(text)
        assert c.geopoint_to_mgrs(gp, source=text) == text, text


def _coords_format(lat, lon, per_axis):
    from opord_builder.openaix.vendor import coordinates

    return coordinates.format_mgrs(lat, lon, per_axis)


def test_mgrs_nudge_recovers_truncation(monkeypatch):
    """A point whose float truncation drops a digit is nudged 1 mm north-east and then matches the source."""
    gp = c.mgrs_to_geopoint("32UMA1500079500")
    real = c._coords.format_mgrs
    calls = []

    def flaky(lat, lon, digits=5):
        calls.append((lat, lon))
        if len(calls) == 1:
            return "32UMA1499979500"
        return real(lat, lon, digits)

    monkeypatch.setattr(c._coords, "format_mgrs", flaky)
    assert c.geopoint_to_mgrs(gp, source="32UMA1500079500") == "32UMA1500079500"
    assert calls[1][0] > calls[0][0] and calls[1][1] > calls[0][1]


# ---- Geometry

G1, G2, G3 = "32UMA1000010000", "32UMA2000010000", "32UMA2000020000"


@pytest.mark.parametrize(
    ("text", "area", "kind"),
    [
        (G1, False, "point"),
        (f"{G1} {G2}", False, "line"),
        (f"{G1}, {G2}; {G3}", False, "line"),
        (f"{G1} to {G2}", False, "line"),
        (f"{G1} {G2} {G3}", True, "polygon"),
        (f"{G1} {G2} {G3} {G1}", True, "polygon"),
        ("32U MA 10000 10000", False, "point"),
        ("Along PL BRONZE NK 05 80 to NK 15 80", False, "description"),
        (f"near {G1}", False, "description"),
        ("32UMA12345", False, "description"),
        (f"{G1} {G2}", True, "description"),  # 2 distinct points cannot close a polygon
    ],
)
def test_to_geometry(text, area, kind):
    geometry = c.to_geometry(text, area)
    assert geometry["kind"] == kind
    assert_valid("Geometry", geometry)


def test_polygon_ring_closed_and_text_round_trip():
    poly = c.to_geometry(f"{G1} {G2} {G3}", area=True)
    ring = poly["rings"][0]
    assert ring[0] == ring[-1] and len(ring) == 4
    assert c.from_geometry(poly) == f"{G1} {G2} {G3}"
    assert c.from_geometry(c.to_geometry(G1)) == G1
    assert c.from_geometry(c.to_geometry(f"{G1} {G2}")) == f"{G1} {G2}"
    assert c.from_geometry(c.to_geometry("some words")) == "some words"


def test_geometry_errors():
    with pytest.raises(c.ConvertError, match="grid_or_trace"):
        c.to_geometry("  ")
    with pytest.raises(c.ConvertError):
        c.from_geometry({"kind": "circle"})


# ---- quantities


def test_altitude():
    a = c.altitude(25000)
    assert a == {"value": 25000, "unit": "ft", "reference": "MSL"}
    assert_valid("Altitude", a)
    assert c.altitude(220, "flight_level", "FL") == {
        "value": 220,
        "unit": "flight_level",
        "reference": "FL",
    }
    assert_valid("Altitude", c.altitude(500, "m", "AGL"))
    assert c.altitude_value(a) == 25000
    for args in [
        (1, "yd"),
        (1, "ft", "XX"),
        (1, "flight_level", "MSL"),
        (1, "ft", "FL"),
    ]:
        with pytest.raises(c.ConvertError, match="altitude"):
            c.altitude(*args)
    with pytest.raises(c.ConvertError, match="unit is"):
        c.altitude_value(c.altitude(500, "m", "AGL"))


def test_altitude_block():
    b = c.altitude_block(18000, 24000)
    assert b == {
        "lower": {"value": 18000, "unit": "ft", "reference": "MSL"},
        "upper": {"value": 24000, "unit": "ft", "reference": "MSL"},
    }
    assert_valid("AltitudeBlock", b)
    assert_valid("AltitudeBlock", c.altitude_block(None, None))
    with pytest.raises(c.ConvertError, match="above ceiling"):
        c.altitude_block(30000, 20000)


@pytest.mark.parametrize(
    ("fn", "unit", "def_name"), [(c.length, "nm", "Length"), (c.speed, "kt", "Speed")]
)
def test_length_speed(fn, unit, def_name):
    v = fn(12.5, unit)
    assert v == {"value": 12.5, "unit": unit}
    assert_valid(def_name, v)
    for bad in (0, -1, "3", True, float("nan")):
        with pytest.raises(c.ConvertError):
            fn(bad, unit)
    with pytest.raises(c.ConvertError, match="unit"):
        fn(1, "parsec")


def test_length_speed_values():
    assert c.length_value(c.length(5, "nm")) == 5
    assert c.speed_value(c.speed(350)) == 350
    with pytest.raises(c.ConvertError):
        c.length_value(c.length(5, "km"))
    assert_valid("Speed", c.speed(0.9, "mach"))
    assert_valid("Length", c.length(2, "km"))


# ---- frequency / channel / TACAN


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("251", {"value": 251.0, "unit": "MHz", "band": "uhf"}),
        ("251.000", {"value": 251.0, "unit": "MHz", "band": "uhf"}),
        ("124.5 MHz", {"value": 124.5, "unit": "MHz", "band": "vhf"}),
        (
            " 124.5MHzAM ",
            {"value": 124.5, "unit": "MHz", "band": "vhf", "modulation": "AM"},
        ),
        ("40.5 FM", {"value": 40.5, "unit": "MHz", "band": "fm", "modulation": "FM"}),
        ("8.9", {"value": 8.9, "unit": "MHz", "band": "hf"}),
        ("100.0", {"value": 100.0, "unit": "MHz"}),  # between bands: no band
        ("30", {"value": 30.0, "unit": "MHz", "band": "fm"}),
        ("400", {"value": 400.0, "unit": "MHz", "band": "uhf"}),
    ],
)
def test_parse_frequency(text, expected):
    f = c.parse_frequency(text)
    assert f == expected
    assert_valid("Frequency", f)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "abc",
        "0",
        "0.0",
        "-5",
        "124.5 kHz",
        "124.5 MHz USB",
        "Ch 3",
        "1,5",
        "124.5.1",
        None,
        124.5,
    ],
)
def test_parse_frequency_bad_names_field(bad):
    with pytest.raises(c.ConvertError, match="comms.net"):
        c.parse_frequency(bad, "comms.net")


@pytest.mark.parametrize(
    ("freq", "text"),
    [
        ({"value": 251.0, "unit": "MHz"}, "251.0 MHz"),
        ({"value": 124.5, "unit": "MHz", "modulation": "AM"}, "124.5 MHz AM"),
        ({"value": 5000, "unit": "kHz"}, "5.0 MHz"),
        ({"value": 8991, "unit": "kHz", "modulation": "FM"}, "8.991 MHz FM"),
    ],
)
def test_format_frequency(freq, text):
    assert c.format_frequency(freq) == text
    assert c.parse_frequency(text)["unit"] == "MHz"


def test_frequency_round_trip_1000():
    rng = random.Random(7)
    for _ in range(1000):
        value = round(rng.uniform(2, 400), rng.choice([0, 1, 2, 3]))
        parsed = c.parse_frequency(f"{value} MHz")
        assert c.parse_frequency(c.format_frequency(parsed)) == parsed


@pytest.mark.parametrize(
    ("text", "n"),
    [
        ("Ch 3", 3),
        ("ch3", 3),
        ("CHANNEL 14", 14),
        ("03", 3),
        ("14", 14),
        (" Ch. 7 ", 7),
    ],
)
def test_channel_to_preset(text, n):
    assert c.channel_to_preset(text) == n
    assert c.channel_to_preset(c.preset_to_channel(n)) == n


@pytest.mark.parametrize("bad", ["HF-A", "", "Ch 0", "Ch", "Ch 3b", None])
def test_channel_bad(bad):
    with pytest.raises(c.ConvertError, match="channel"):
        c.channel_to_preset(bad)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("11Y", {"channel": 11, "band": "Y"}),
        ("126x", {"channel": 126, "band": "X"}),
        (" 1 X ", {"channel": 1, "band": "X"}),
    ],
)
def test_tacan(text, expected):
    t = c.parse_tacan(text)
    assert t == expected
    assert_valid("TACAN", t)
    assert c.format_tacan(t) == text.strip().replace(" ", "").upper()


def test_tacan_identifier_and_bad():
    assert c.parse_tacan("73X", "TEX")["identifier"] == "TEX"
    for bad in ("0X", "127X", "11", "11Z", "X11", ""):
        with pytest.raises(c.ConvertError, match="tacan"):
            c.parse_tacan(bad)


# ---- slug / catalogues


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Viper 1", "viper-1"),
        ("  Hello,   World!! ", "hello-world"),
        ("1st Fighter Wing", "x-1st-fighter-wing"),
        ("Spangdahlem AB (ETAR)", "spangdahlem-ab-etar"),
        ("Zürich", "zurich"),
        ("A_B", "a-b"),
    ],
)
def test_slug(name, expected):
    s = c.slug(name)
    assert s == expected
    assert_valid("Identifier", s)


def test_slug_collisions_and_errors():
    assert c.assign_ids(["Viper 1", "viper-1", "VIPER 1", "Other"]) == [
        "viper-1",
        "viper-1-2",
        "viper-1-3",
        "other",
    ]
    taken = {"a"}
    assert c.slug("A", taken) == "a-2" and taken == {"a", "a-2"}
    for bad in ("", "!!!", "日本"):
        with pytest.raises(c.ConvertError, match="name"):
            c.slug(bad)


def test_resolve_names_lists_all_misses():
    cat = {
        "viper-1": {"name": "Viper 1"},
        "ford": {"name": "Ford"},
        "d1": {"name": "Dup"},
        "d2": {"name": "Dup"},
    }
    assert c.resolve_names(["Ford", "Viper 1"], cat) == {
        "Ford": "ford",
        "Viper 1": "viper-1",
    }
    with pytest.raises(c.UnresolvedNames) as info:
        c.resolve_names(["Ford", "Nope", "viper 1", "Dup"], cat, "callsign")
    assert info.value.misses[:2] == ["Nope", "viper 1"]
    assert "ambiguous" in info.value.misses[2]
    assert (
        "callsign" in str(info.value)
        and "'Nope'" in str(info.value)
        and "'viper 1'" in str(info.value)
    )
    assert c.names_for_ids(["ford"], cat) == {"ford": "Ford"}
    with pytest.raises(c.UnresolvedNames):
        c.names_for_ids(["ford", "zzz", "yyy"], cat)


# ---- enums


@pytest.mark.parametrize(
    ("enum", "authored", "openaix"),
    [
        ("target_timing", "Immediate", "immediate"),
        ("target_timing", "As Acquired", "as_acquired"),
        ("desired_effect", "NEUTRALIZE", "neutralize"),
        ("cas_control_type", "TYPE_2", "type_2"),
        ("cas_mark", "IR_POINTER", "infrared"),
        ("cas_mark", "WP", "white_phosphorus"),
        ("coa_designation", "MDCOA", "most_dangerous"),
        ("command_relationship", "OPCON", "operational_control"),
        ("command_relationship", "GSR", "general_support_reinforcing"),
        ("classification", "TOP SECRET", "TOP SECRET"),
    ],
)
def test_enum_tables(enum, authored, openaix):
    assert c.map_enum(enum, authored) == openaix
    assert c.unmap_enum(enum, openaix) == authored


def test_enum_unknown_never_lowercases():
    with pytest.raises(c.ConvertError, match="valid:"):
        c.map_enum("target_timing", "immediate", "hpt.timing")
    with pytest.raises(c.ConvertError, match="hpt.timing"):
        c.map_enum("target_timing", "IMMEDIATE", "hpt.timing")
    with pytest.raises(c.ConvertError):
        c.map_enum("cas_mark", "GOGGLES")
    with pytest.raises(c.ConvertError):
        c.unmap_enum("cas_mark", "nope")
    assert c.unmap_enum("coa_designation", "other") == "COA_3"


def test_enum_values_exist_in_openaix_schema():
    """Every mapped value that has a schema enum counterpart is in the vendored opord schema."""
    enums: dict[str, set] = {}

    def walk(node, name=""):
        if isinstance(node, dict):
            if "enum" in node:
                enums.setdefault(name, set()).update(node["enum"])
            for k, v in node.items():
                walk(v, k if k != "properties" else name)
        elif isinstance(node, list):
            for v in node:
                walk(v, name)

    walk(schemas()["opord"])
    expect = {
        "target_timing": "timing",
        "desired_effect": "effect",
        "cas_control_type": "control_type",
        "cas_mark": "mark",
        "coa_designation": "kind",
        "command_relationship": "relationship",
    }
    for enum, prop in expect.items():
        assert set(c.ENUMS[enum].values()) <= enums[prop], enum


# ---- control measures


@pytest.mark.parametrize(
    ("code", "resolved", "extension", "values"),
    [
        ("ROZ", "ROZ", False, {}),
        ("HIDACZ", "HIDACZ", False, {}),
        ("HIMEZ", "MEZ", False, {"mez_kind": "high"}),
        ("LOMEZ", "MEZ", False, {"mez_kind": "low"}),
        ("SAFE", "SAFES", False, {}),
        ("SAFES", "SAFES", False, {}),
        ("ROA", "ROZ", False, {}),
        ("FSCL", "FSCL", False, {}),
        ("BULLSEYE", "BULLSEYE", False, {}),
        ("POINT", "POINT", False, {}),
        ("AXIS", "AXIS", True, {}),
        ("CFZ", "CFZ", True, {}),
        ("SFA", "SFA", True, {}),
        ("RFZ", "RFA", False, {}),
        ("SAR", "SARDOT", True, {}),
    ],
)
def test_measure_type(code, resolved, extension, values):
    m = c.measure_type(code)
    assert (
        m["code"] == resolved and m["extension"] is extension and m["values"] == values
    )
    assert (m["namespace"] == "org.opord-builder.measure") is extension
    if not extension and code not in c.CANONICAL_KINDS:
        assert m["schema"].startswith("urn:openaix:schema:")


def test_measure_type_alias_recorded_and_case_exact():
    assert c.measure_type("HIMEZ")["alias_of"] == "HIMEZ"
    assert c.measure_type("ROZ")["alias_of"] is None
    for bad in ("roz", "Himez", "WAYPOINT", "ANCHOR", ""):
        with pytest.raises(c.ConvertError, match="type"):
            c.measure_type(bad)


def test_every_authoring_airspace_kind_and_georef_kind_is_handled():
    """Authoring kinds either map or are one of the documented unmapped georef kinds."""
    from typing import get_args

    from opord_builder.schema import shared

    for kind in get_args(shared.AirspaceZoneKind):
        c.measure_type(kind)
    unmapped = set()
    for kind in get_args(shared.GeoRefKind):
        try:
            c.measure_type(kind)
        except c.ConvertError:
            unmapped.add(kind)
    assert unmapped <= {
        "ANCHOR",
        "WAYPOINT",
        "EGRESS_PT",
        "FIX",
        "TACAN",
        "NAVAID",
        "OTHER",
    }, unmapped


# ---- frequencies found anywhere in the vendored examples


def _frequency_property_names() -> set[str]:
    names: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for key, sub in (node.get("properties") or {}).items():
                if '/$defs/Frequency"' in json.dumps(sub):
                    names.add(key)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for schema in schemas().values():
        walk(schema)
    return names


def _collect(node, names, path, out):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in names:
                for item in v if isinstance(v, list) else [v]:
                    out.append((path + "/" + k, item))
            _collect(v, names, f"{path}/{k}", out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _collect(v, names, f"{path}/{i}", out)


def test_every_example_frequency_parses():
    names = _frequency_property_names()
    assert {
        "frequency"
    } <= names or names  # Frequency-typed properties exist in the schemas
    found, failures = [], []
    for path in sorted((VENDOR_DIR / "examples").glob("*/*.json")):
        hits: list = []
        _collect(json.loads(path.read_text()), names, "", hits)
        for pointer, item in hits:
            found.append(item)
            # Frequency-typed fields are objects; a string under a same-named field (e.g. a report interval) is
            # another type. The object is rendered to its authored text form and parsed back.
            if not (isinstance(item, dict) and "value" in item and "unit" in item):
                continue
            text = c.format_frequency(item)
            try:
                parsed = c.parse_frequency(text)
                if isinstance(item, dict):
                    mhz = (
                        item["value"] / 1000 if item["unit"] == "kHz" else item["value"]
                    )
                    assert parsed["value"] == pytest.approx(mhz)
                    if "modulation" in item:
                        assert parsed["modulation"] == item["modulation"]
            except c.ConvertError as exc:
                failures.append(f"{path.parent.name}/{path.name}{pointer}: {exc}")
    assert found, "no frequencies found in the vendored examples"
    assert not failures, "unparseable frequencies:\n" + "\n".join(failures)
