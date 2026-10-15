"""Build SPINS tables from typed OpenAIX data (the `openaix_table` block)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from opord_builder.openaix import convert
from opord_builder.openaix.validate import validate
from opord_builder.schema.spins import (
    NoteBlock,
    OpenAIXTableBlock,
    SpinsOpenAIXRefs,
    TableBlock,
)

SOURCES = ("ato", "aco", "spins", "resources", "airfield")
# Documents of each source must carry one of these `kind` values.
KINDS = {
    "ato": {"ato"},
    "aco": {"aco"},
    "spins": {"spins"},
    "resources": {"resources"},
    "airfield": {"airfield", "carrier", "farp"},
}
MAX_LISTED_ERRORS = 5
_MISSING = object()


class OpenAIXTableError(ValueError):
    """An `openaix_table` cannot be built; the message names the block and pointer."""


def _label(block: OpenAIXTableBlock) -> str:
    return f"openaix_table {block.id or block.caption!r}"


# --------------------------------------------------------------------------- JSON Pointer


def _tokens(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError(
            f"not a JSON Pointer (must be '' or start with '/'): {pointer!r}"
        )
    return [t.replace("~1", "/").replace("~0", "~") for t in pointer[1:].split("/")]


def resolve(document: Any, pointer: str) -> Any:
    """The value at `pointer`, or `_MISSING` when a key or index is absent.

    Descending into a scalar is an error (the pointer is wrong, not the data)."""
    value = document
    walked = ""
    for token in _tokens(pointer):
        if isinstance(value, dict):
            if token not in value:
                return _MISSING
            value = value[token]
        elif isinstance(value, list):
            if not token.isdigit() or int(token) >= len(value):
                return _MISSING
            value = value[int(token)]
        else:
            raise ValueError(  # noqa: TRY004
                f"cannot descend into {type(value).__name__} at {walked or '/'!r}"
                f" with token {token!r}"
            )
        walked += "/" + token
    return value


# --------------------------------------------------------------------------- value text

_VERTICAL_WORDS = {"surface": "SFC", "unlimited": "UNL"}
_RECOVERY_CASES = {"case_i": "Case I", "case_ii": "Case II", "case_iii": "Case III"}


def _number(value: float) -> str:
    return format(Decimal(str(value)).normalize(), "f")


def _altitude(alt: dict[str, Any]) -> str:
    if alt["unit"] == "flight_level":
        return f"FL{int(alt['value']):03d}"
    return f"{_number(alt['value'])} {alt['unit']} {alt['reference']}"


def _bearing(b: dict[str, Any]) -> str:
    value = b["value"]
    text = f"{int(value):03d}" if float(value).is_integer() else f"{value:05.1f}"
    return f"{text}° {'M' if b['reference'] == 'magnetic' else 'T'}"


def _time(value: Any, where: str) -> str:
    if isinstance(value, str):
        try:
            return convert.rfc3339_to_dtg(value, where, warnings=[])
        except convert.ConvertError:
            return value
    if isinstance(value, dict) and "offset_minutes" in value:
        minutes = value["offset_minutes"]
        return f"T{'+' if minutes >= 0 else '-'}{_number(abs(minutes))} min"
    raise ValueError(f"{where}: unrecognized time value")


def format_value(value: Any, where: str = "value") -> str:
    """Human text for an OpenAIX value; raises ValueError for an object it cannot read."""
    if value is None or value is _MISSING:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return _number(value)
    if isinstance(value, str):
        return _time(value, where) if value[:4].isdigit() and "T" in value else value
    if isinstance(value, list):
        parts = [format_value(item, f"{where}[{i}]") for i, item in enumerate(value)]
        return ", ".join(part for part in parts if part)
    if isinstance(value, dict):
        keys = set(value)
        unit = value.get("unit")
        if keys == {"surface"} or keys == {"unlimited"}:
            return _VERTICAL_WORDS[next(iter(keys))]
        if keys == {"offset_minutes"}:
            return _time(value, where)
        if "lower" in keys and "upper" in keys:
            return f"{format_value(value['lower'], where)} to {format_value(value['upper'], where)}"
        if unit in ("MHz", "kHz") and "value" in keys:
            return convert.format_frequency(value, where)
        if "reference" in keys and unit in ("ft", "m", "flight_level"):
            return _altitude(value)
        if "reference" in keys and "value" in keys and unit is None:
            return _bearing(value)
        if "value" in keys and unit is not None:
            return f"{_number(value['value'])} {unit}"
        if {"channel", "band"} <= keys:
            text = convert.format_tacan(value)
            return (
                f"{text} ({value['identifier']})" if value.get("identifier") else text
            )
        if {"case", "window"} <= keys:  # a carrier RecoveryWindow
            text = f"{_RECOVERY_CASES.get(value['case'], value['case'])} {format_value(value['window'], where)}"
            if value.get("brc"):
                text += f", BRC {_bearing(value['brc'])}"
            return text
        if {"start", "end"} <= keys:
            return f"{_time(value['start'], where)} to {_time(value['end'], where)}"
        if {"latitude", "longitude"} <= keys:
            return f"{_number(value['latitude'])}, {_number(value['longitude'])}"
        if isinstance(value.get("frequency"), dict):
            who = value.get("callsign") or value.get("role") or value.get("name")
            freq = convert.format_frequency(value["frequency"], where)
            return f"{who} {freq}" if who else freq
        raise ValueError(
            f"{where}: an object with keys {sorted(keys)} has no text form;"
            " point the column at one of its scalar members"
        )
    raise ValueError(f"{where}: unsupported value {value!r}")


def _describe(identifier: str, record: Any) -> str:
    """Identifier -> short human description of the record it names."""
    if not isinstance(record, dict):
        return identifier
    name = record.get("name") or record.get("callsign") or identifier
    if isinstance(record.get("frequency"), dict):
        return f"{name} ({convert.format_frequency(record['frequency'])})"
    if record.get("ident"):
        return f"{name} ({record['ident']})"
    return str(name)


# --------------------------------------------------------------------------- sources


class OpenAIXSources:
    """Lazily loads, validates and caches the OpenAIX files named by a SPINS `openaix` section."""

    def __init__(self, refs: SpinsOpenAIXRefs | None, directory: Path):
        self.refs = refs
        self.directory = Path(directory)
        self._cache: dict[str, list[tuple[Path, Any]]] = {}
        self._lookups: dict[str, dict[str, Any]] = {}

    def paths(self, source: str) -> list[Path]:
        if self.refs is None:
            return []
        if source == "airfield":
            names = list(self.refs.airfields)
        else:
            name = getattr(self.refs, source)
            names = [name] if name else []
        return [self.directory / name for name in names]

    def documents(self, source: str) -> list[tuple[Path, Any]]:
        if source not in self._cache:
            self._cache[source] = [self._load(source, p) for p in self.paths(source)]
        return self._cache[source]

    @staticmethod
    def _load(source: str, path: Path) -> tuple[Path, Any]:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise OpenAIXTableError(
                f"openaix {source} file {path}: {exc.strerror or exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise OpenAIXTableError(
                f"openaix {source} file {path}: invalid JSON: {exc}"
            ) from exc
        errors = validate(document)
        if errors:
            shown = "; ".join(str(e) for e in errors[:MAX_LISTED_ERRORS])
            more = len(errors) - MAX_LISTED_ERRORS
            raise OpenAIXTableError(
                f"openaix {source} file {path} is not valid OpenAIX: {shown}"
                + (f"; and {more} more" if more > 0 else "")
            )
        kind = document.get("kind")
        if kind not in KINDS[source]:
            raise OpenAIXTableError(
                f"openaix {source} file {path}: kind is {kind!r}, expected {sorted(KINDS[source])}"
            )
        return path, document

    def lookup(self, spec: str) -> dict[str, Any]:
        """Records for a column `lookup`: 'airfield', or '<source>:<pointer to a map keyed by id>'."""
        if spec not in self._lookups:
            source, _, pointer = spec.partition(":")
            if source not in SOURCES:
                raise OpenAIXTableError(f"lookup {spec!r}: unknown source {source!r}")
            records: dict[str, Any] = {}
            for path, document in self.documents(source):
                if source == "airfield" and not pointer:
                    records[str(document.get("id"))] = document
                    continue
                try:
                    found = resolve(document, pointer)
                except ValueError as exc:
                    raise OpenAIXTableError(
                        f"lookup {spec!r} in {path}: {exc}"
                    ) from exc
                if isinstance(found, dict):
                    records.update(found)
                elif found is not _MISSING:
                    raise OpenAIXTableError(
                        f"lookup {spec!r} in {path}: {pointer!r} must be a map keyed by id"
                    )
            self._lookups[spec] = records
        return self._lookups[spec]


# --------------------------------------------------------------------------- tables


def _rows(block: OpenAIXTableBlock, sources: OpenAIXSources) -> list[tuple[Any, Any]]:
    """(key, row value) pairs from every document of the block's source."""
    out: list[tuple[Any, Any]] = []
    for path, document in sources.documents(block.source):
        try:
            target = resolve(document, block.pointer)
        except ValueError as exc:
            raise OpenAIXTableError(
                f"{_label(block)}: pointer {block.pointer!r} in {path}: {exc}"
            ) from exc
        if target is _MISSING or target is None:
            continue
        mode = block.rows
        if mode == "auto":
            mode = "items" if isinstance(target, list) else "single"
        if mode == "items" and not isinstance(target, list):
            raise OpenAIXTableError(
                f"{_label(block)}: pointer {block.pointer!r} in {path} must be an array for rows: items"
            )
        if mode == "entries" and not isinstance(target, dict):
            raise OpenAIXTableError(
                f"{_label(block)}: pointer {block.pointer!r} in {path} must be a map for rows: entries"
            )
        if not isinstance(target, (list, dict)):
            raise OpenAIXTableError(
                f"{_label(block)}: pointer {block.pointer!r} in {path} is a"
                f" {type(target).__name__}; point at an array, a map or an object"
            )
        if mode == "items":
            out.extend((index, item) for index, item in enumerate(target))
        elif mode == "entries":
            out.extend(target.items())
        else:
            out.append((None, target))
    return out


def _cell(block, column, key, row, sources: OpenAIXSources) -> str:
    where = f"{_label(block)}: column {column.key!r} field {column.field!r}"
    if column.field == "#key":
        value = key
    else:
        try:
            value = resolve(row, column.field)
        except ValueError as exc:
            raise OpenAIXTableError(f"{where}: {exc}") from exc
    if column.lookup and value not in (_MISSING, None):
        records = sources.lookup(column.lookup)
        ids = value if isinstance(value, list) else [value]
        if not all(isinstance(i, (str, int)) for i in ids):
            raise OpenAIXTableError(f"{where}: lookup needs identifiers")
        return ", ".join(_describe(str(i), records.get(str(i))) for i in ids)
    try:
        return format_value(value, where)
    except ValueError as exc:
        raise OpenAIXTableError(
            f"{_label(block)}: column {column.key!r}: {exc}"
        ) from exc


def openaix_table(
    block: OpenAIXTableBlock, sources: OpenAIXSources
) -> TableBlock | NoteBlock | None:
    """The finished table, a 'not provided' note, or None when the block is to be skipped."""
    rows: list[dict[str, str]] = []
    for key, row in _rows(block, sources):
        if not all(_present(_safe(row, pointer)) for pointer in block.require):
            continue
        rows.append({c.key: _cell(block, c, key, row, sources) for c in block.columns})
    if rows:
        return TableBlock(
            kind="table",
            id=block.id,
            caption=block.caption,
            columns=[
                c.model_dump(include={"key", "heading", "align"}) for c in block.columns
            ],
            rows=rows,
        )
    if block.empty == "skip":
        return None
    if block.empty == "notice":
        return NoteBlock(
            kind="note",
            id=block.id,
            heading="NOT PROVIDED",
            text=f"No {block.source} data was provided for: {block.caption}.",
        )
    configured = sources.paths(block.source)
    reason = (
        f"no {block.source} file is listed under openaix"
        if not configured
        else f"nothing at that pointer in {', '.join(str(p) for p in configured)}"
    )
    raise OpenAIXTableError(
        f"{_label(block)}: pointer {block.pointer!r} gave no rows ({reason})"
    )


def _safe(row: Any, pointer: str) -> Any:
    try:
        return _MISSING if pointer == "#key" else resolve(row, pointer)
    except ValueError:
        return _MISSING


def _present(value: Any) -> bool:
    return value is not _MISSING and value not in (None, "", [], {})
