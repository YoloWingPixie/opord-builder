"""Text coordinate formats for WGS 84 positions. Files store decimal degrees; the tools read and print these forms.

- PackedDMS: hemisphere, degrees, minutes and seconds with hundredths, no separators: `N40154835W104460637`
  (latitude `DDMMSSss`, longitude `DDDMMSSss`). The parser also reads ten-thousandths of a second.
- ICAO DMS and DM: hemisphere after the value: `401548N1044606W`, `4015N10446W`.
- MGRS: zone, latitude band, 100 km square and an even number of digits: `13SED1234567890`. MGRS covers
  80S to 84N; the polar UPS areas are not supported. A reference names the south-west corner of its square, and
  formatting truncates, as MGRS does. The corner of a square on a zone edge can lie in the next zone.

`parse(text)` detects the format and returns `(latitude, longitude)`. Invalid text raises ValueError.
"""
import math
import re


# PackedDMS and ICAO forms

def _check(latitude, longitude):
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("coordinate outside geographic bounds: %r, %r" % (latitude, longitude))


def _value(hemisphere, degrees, minutes, seconds=0, axis="NS"):
    if hemisphere not in axis:
        raise ValueError("invalid hemisphere letter: " + hemisphere)
    if minutes >= 60 or seconds >= 60:
        raise ValueError("invalid coordinate minutes or seconds")
    result = degrees + minutes / 60 + seconds / 3600
    if result > (90 if axis == "NS" else 180):
        raise ValueError("coordinate outside geographic bounds")
    return round(result * (-1 if hemisphere in "SW" else 1), 10)


def packed_dms_value(text):
    """One PackedDMS half (`N40154835` or `W104460637`) as signed decimal degrees."""
    if not re.fullmatch(r"[NS]\d{8}(?:\d{2})?|[EW]\d{9}(?:\d{2})?", text):
        raise ValueError("invalid PackedDMS coordinate: " + repr(text))
    width = 2 if text[0] in "NS" else 3
    digits = text[width + 5:]
    return _value(text[0], int(text[1:width + 1]), int(text[width + 1:width + 3]),
                  int(text[width + 3:]) / 10 ** len(digits), "NS" if width == 2 else "EW")


def parse_packed_dms(text):
    match = re.fullmatch(r"([NS]\d{8}(?:\d{2})?)([EW]\d{9}(?:\d{2})?)", text)
    if not match:
        raise ValueError("invalid PackedDMS position: " + repr(text))
    return packed_dms_value(match[1]), packed_dms_value(match[2])


def parse_icao(text):
    """ICAO DMS (`401548N1044606W`) or DM (`4015N10446W`)."""
    match = (re.fullmatch(r"(\d{2})(\d{2})(\d{2})([NS])(\d{3})(\d{2})(\d{2})([EW])", text)
             or re.fullmatch(r"(\d{2})(\d{2})()([NS])(\d{3})(\d{2})()([EW])", text))
    if not match:
        raise ValueError("invalid ICAO position: " + repr(text))
    parts = match.groups()
    number = lambda digits: int(digits) if digits else 0
    return (_value(parts[3], int(parts[0]), int(parts[1]), number(parts[2]), "NS"),
            _value(parts[7], int(parts[4]), int(parts[5]), number(parts[6]), "EW"))


def _split(value, units, axis):
    """Signed degrees as (hemisphere, degrees, minutes, sub-minute units), rounded to 1/units of a minute."""
    total = round(abs(value) * 60 * units)
    hemisphere = axis[1] if value < 0 and total else axis[0]
    minutes, rest = divmod(total, units)
    degrees, minutes = divmod(minutes, 60)
    return hemisphere, degrees, minutes, rest


def format_packed_dms(latitude, longitude):
    _check(latitude, longitude)
    text = ""
    for value, axis, width in ((latitude, "NS", 2), (longitude, "EW", 3)):
        hemisphere, degrees, minutes, hundredths = _split(value, 6000, axis)
        text += "%s%0*d%02d%04d" % (hemisphere, width, degrees, minutes, hundredths)
    return text


def format_icao_dms(latitude, longitude):
    _check(latitude, longitude)
    text = ""
    for value, axis, width in ((latitude, "NS", 2), (longitude, "EW", 3)):
        hemisphere, degrees, minutes, seconds = _split(value, 60, axis)
        text += "%0*d%02d%02d%s" % (width, degrees, minutes, seconds, hemisphere)
    return text


def format_icao_dm(latitude, longitude):
    _check(latitude, longitude)
    text = ""
    for value, axis, width in ((latitude, "NS", 2), (longitude, "EW", 3)):
        hemisphere, degrees, minutes, _ = _split(value, 1, axis)
        text += "%0*d%02d%s" % (width, degrees, minutes, hemisphere)
    return text


# UTM and MGRS on WGS 84 (Krüger series to fourth order in n; Karney 2011)

A_AXIS = 6378137.0
FLATTENING = 1 / 298.257223563
K0 = 0.9996
_N = FLATTENING / (2 - FLATTENING)
_RECTIFYING = A_AXIS / (1 + _N) * (1 + _N ** 2 / 4 + _N ** 4 / 64)
_ALPHA = (_N / 2 - 2 * _N ** 2 / 3 + 5 * _N ** 3 / 16 + 41 * _N ** 4 / 180,
          13 * _N ** 2 / 48 - 3 * _N ** 3 / 5 + 557 * _N ** 4 / 1440,
          61 * _N ** 3 / 240 - 103 * _N ** 4 / 140,
          49561 * _N ** 4 / 161280)
_BETA = (_N / 2 - 2 * _N ** 2 / 3 + 37 * _N ** 3 / 96 - _N ** 4 / 360,
         _N ** 2 / 48 + _N ** 3 / 15 - 437 * _N ** 4 / 1440,
         17 * _N ** 3 / 480 - 37 * _N ** 4 / 840,
         4397 * _N ** 4 / 161280)
_E = 2 * math.sqrt(_N) / (1 + _N)
BANDS = "CDEFGHJKLMNPQRSTUVWX"
COLUMNS = ("ABCDEFGH", "JKLMNPQR", "STUVWXYZ")
ROWS = "ABCDEFGHJKLMNPQRSTUV"


def utm_zone(latitude, longitude):
    if longitude == 180:
        return 60
    zone = int((longitude + 180) // 6) + 1
    if 56 <= latitude < 64 and 3 <= longitude < 12:
        return 32
    if 72 <= latitude <= 84 and 0 <= longitude < 42:
        return 31 if longitude < 9 else 33 if longitude < 21 else 35 if longitude < 33 else 37
    return zone


def to_utm(latitude, longitude, zone):
    """UTM easting and northing in metres; the southern hemisphere uses the 10 000 km false northing."""
    phi, lam = math.radians(latitude), math.radians(longitude - (zone * 6 - 183))
    t = math.sinh(math.atanh(math.sin(phi)) - _E * math.atanh(_E * math.sin(phi)))
    xi, eta = math.atan2(t, math.cos(lam)), math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    x = eta + sum(a * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j, a in enumerate(_ALPHA, 1))
    y = xi + sum(a * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j, a in enumerate(_ALPHA, 1))
    return 500000 + K0 * _RECTIFYING * x, K0 * _RECTIFYING * y + (10000000 if latitude < 0 else 0)


def from_utm(easting, northing, zone, south):
    xi = (northing - (10000000 if south else 0)) / (K0 * _RECTIFYING)
    eta = (easting - 500000) / (K0 * _RECTIFYING)
    xi1 = xi - sum(b * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j, b in enumerate(_BETA, 1))
    eta1 = eta - sum(b * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j, b in enumerate(_BETA, 1))
    conformal = math.sin(xi1) / math.hypot(math.sinh(eta1), math.cos(xi1))
    tau = conformal
    for _ in range(5):  # Newton iteration from the conformal latitude to the geodetic latitude (Karney 2011)
        sigma = math.sinh(_E * math.atanh(_E * tau / math.hypot(1, tau)))
        estimate = tau * math.hypot(1, sigma) - sigma * math.hypot(1, tau)
        tau += ((conformal - estimate) / math.hypot(1, estimate)
                * (1 + (1 - _E ** 2) * tau ** 2) / ((1 - _E ** 2) * math.hypot(1, tau)))
    lam = math.atan2(math.sinh(eta1), math.cos(xi1))
    return math.degrees(math.atan(tau)), zone * 6 - 183 + math.degrees(lam)


def format_mgrs(latitude, longitude, digits=5):
    """MGRS reference with `digits` digits each for easting and northing (5 is 1 m)."""
    _check(latitude, longitude)
    if not -80 <= latitude <= 84:
        raise ValueError("MGRS covers 80S to 84N; polar UPS is not supported")
    if digits not in range(6):
        raise ValueError("MGRS precision is 0 to 5 digits")
    zone = utm_zone(latitude, longitude)
    # Truncate to whole metres; the small offset keeps a value such as 23486.9999999 from an exact inverse at 23487.
    easting, northing = (int(math.floor(value + 1e-6)) for value in to_utm(latitude, longitude, zone))
    band = BANDS[min(int((latitude + 80) // 8), 19)]
    column = COLUMNS[(zone - 1) % 3][easting // 100000 - 1]
    row = ROWS[(northing // 100000 + (5 if zone % 2 == 0 else 0)) % 20]
    scale = 10 ** (5 - digits)
    east, north = (value % 100000 // scale for value in (easting, northing))
    return "%02d%s%s%s%s" % (zone, band, column, row, "%0*d%0*d" % (digits, east, digits, north) if digits else "")


def parse_mgrs(text):
    match = re.fullmatch(r"(\d{1,2})([C-HJ-NP-X])([A-HJ-NP-Z])([A-HJ-NP-V])(\d*)", text)
    if not match or len(match[5]) % 2 or len(match[5]) > 10:
        raise ValueError("invalid MGRS reference: " + repr(text))
    zone, band, column, row, numbers = int(match[1]), match[2], match[3], match[4], match[5]
    if not 1 <= zone <= 60:
        raise ValueError("invalid MGRS zone: " + match[1])
    if column not in COLUMNS[(zone - 1) % 3]:
        raise ValueError("MGRS column letter does not belong to zone %d: %s" % (zone, column))
    half = len(numbers) // 2
    scale = 10 ** (5 - half)
    easting = (COLUMNS[(zone - 1) % 3].index(column) + 1) * 100000 + (int(numbers[:half]) * scale if half else 0)
    northing = (ROWS.index(row) - (5 if zone % 2 == 0 else 0)) % 20 * 100000 + (int(numbers[half:]) * scale if half else 0)
    south_edge = BANDS.index(band) * 8 - 80
    north_edge = 84 if band == "X" else south_edge + 8
    south = band < "N"
    for cycle in range(5):
        latitude, longitude = from_utm(easting, northing + cycle * 2000000, zone, south)
        # A 100 km square can cross a band edge, so the south-west corner can be up to one square outside the band.
        if south_edge - 1 <= latitude < north_edge + 1:
            return latitude, longitude
    raise ValueError("MGRS square %s%s is not in band %s of zone %d" % (column, row, band, zone))


# Detection

def parse(text):
    """Read a position in any supported format as (latitude, longitude) in decimal degrees."""
    compact = re.sub(r"\s+", "", str(text)).upper()
    if compact[:1] in ("N", "S"):
        return parse_packed_dms(compact)
    if re.fullmatch(r"\d+[NS]\d+[EW]", compact):
        return parse_icao(compact)
    if re.fullmatch(r"\d{1,2}[A-Z]{3}\d*", compact):
        return parse_mgrs(compact)
    raise ValueError("unrecognized coordinate format: " + repr(text))
