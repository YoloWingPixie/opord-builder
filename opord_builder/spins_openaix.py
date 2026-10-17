"""Build SPINS tables from typed OpenAIX data (the `openaix_table` block)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opord_builder import format as fmt
from opord_builder.format import FORECAST_HEAD, forecast_row
from opord_builder.load import DocumentError, load_document
from opord_builder.pointer import MISSING, resolve
from opord_builder.schema.spins import (
    NoteBlock,
    OpenAIXTableBlock,
    SpinsOpenAIXRefs,
    TableBlock,
    WeatherBlock,
)

SOURCES = (
    "opord",
    "ato",
    "aco",
    "spins",
    "resources",
    "airfield",
    "comms_standard",
)
# Documents of each source must carry one of these `kind` values.
KINDS = {
    "opord": {"opord"},
    "ato": {"ato"},
    "aco": {"aco"},
    "spins": {"spins"},
    "resources": {"resources"},
    "comms_standard": {"comms_standard"},
    "airfield": {"airfield", "carrier", "farp"},
}
_MISSING = MISSING


class OpenAIXTableError(ValueError):
    """An `openaix_table` cannot be built; the message names the block and pointer."""


def _label(block: OpenAIXTableBlock) -> str:
    return f"openaix_table {block.id or block.caption!r}"


# --------------------------------------------------------------------------- value text


def _time(value: Any, where: str) -> str:
    if isinstance(value, str) or (
        isinstance(value, dict) and "offset_minutes" in value
    ):
        return fmt.window(value)
    raise ValueError(f"{where}: unrecognized time value")


def format_value(value: Any, where: str = "value") -> str:
    """Human text for an OpenAIX value; raises ValueError for an object it cannot read."""
    if value is None or value is _MISSING:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return fmt.number(value)
    if isinstance(value, str):
        return fmt.dtg(value) if fmt.RFC3339.fullmatch(value) else value
    if isinstance(value, list):
        parts = [format_value(item, f"{where}[{i}]") for i, item in enumerate(value)]
        return ", ".join(part for part in parts if part)
    if isinstance(value, dict):
        keys = set(value)
        unit = value.get("unit")
        if keys in ({"surface"}, {"unlimited"}):
            return fmt.VERTICAL[next(iter(keys))]
        if keys == {"offset_minutes"}:
            return _time(value, where)
        if "lower" in keys and "upper" in keys:
            return f"{format_value(value['lower'], where)} to {format_value(value['upper'], where)}"
        if unit in ("MHz", "kHz") and "value" in keys:
            return fmt.frequency(value)
        if "reference" in keys and unit in ("ft", "m", "flight_level"):
            return fmt.altitude(value)
        if "reference" in keys and "value" in keys and unit is None:
            return fmt.bearing(value)
        if "value" in keys and unit is not None:
            return f"{fmt.number(value['value'])} {unit}"
        if {"channel", "band"} <= keys:
            return fmt.tacan(value)
        if {"case", "window"} <= keys:  # a carrier RecoveryWindow
            text = f"{fmt.CASES.get(value['case'], value['case'])} {format_value(value['window'], where)}"
            if value.get("brc"):
                text += f", BRC {fmt.bearing(value['brc'])}"
            return text
        if {"start", "end"} <= keys:
            return f"{_time(value['start'], where)} to {_time(value['end'], where)}"
        if {"latitude", "longitude"} <= keys:
            return f"{fmt.number(value['latitude'])}, {fmt.number(value['longitude'])}"
        if isinstance(value.get("frequency"), dict):
            who = value.get("callsign") or value.get("role") or value.get("name")
            freq = fmt.frequency(value["frequency"])
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
        return f"{name} ({fmt.frequency(record['frequency'])})"
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
            document = load_document(path)
        except DocumentError as exc:
            shown = "; ".join(
                f"{e.pointer or '/'}: {e.message}" for e in exc.errors[:5]
            )
            raise OpenAIXTableError(
                f"openaix {source} file {path} is not valid OpenAIX: {shown}"
            ) from exc
        kind = document.get("kind") if isinstance(document, dict) else None
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


def weather_table(
    block: WeatherBlock, sources: OpenAIXSources
) -> TableBlock | NoteBlock | None:
    """The forecast table of a weather block: the same cells as the order's paragraph 1."""
    forecasts: list[dict] = []
    for path, document in sources.documents(block.source):
        try:
            target = resolve(document, block.pointer)
        except ValueError as exc:
            raise OpenAIXTableError(
                f"weather {block.id or block.caption!r}: pointer {block.pointer!r} in {path}: {exc}"
            ) from exc
        if isinstance(target, dict):
            target = target.get("forecasts")
        if isinstance(target, list):
            forecasts += target
    rows = [forecast_row(f, {}) for f in forecasts]
    cols = [c for c in FORECAST_HEAD if any(r[c] for r in rows)]
    if rows:
        return TableBlock(
            kind="table",
            id=block.id,
            caption=block.caption,
            columns=[{"key": c, "heading": FORECAST_HEAD[c]} for c in cols],
            rows=[{c: r[c] for c in cols} for r in rows],
        )
    if block.empty == "skip":
        return None
    if block.empty == "notice":
        return NoteBlock(
            kind="note",
            id=block.id,
            heading="NOT PROVIDED",
            text=f"No weather was provided for: {block.caption}.",
        )
    raise OpenAIXTableError(
        f"weather {block.id or block.caption!r}: pointer {block.pointer!r} gave no forecasts"
    )
