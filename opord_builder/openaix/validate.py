"""Validate OpenAIX documents against the vendored schemas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from opord_builder.openaix.registry import registry, schema_for_id, schemas

# Record kinds that one schema validates under another name (carriers and FARPs are airfield records).
KIND_SCHEMAS = {
    "carrier": "airfield",
    "farp": "airfield",
    "comms_standard": "comms-standard",
}

FORMAT_CHECKER = FormatChecker()
if "date-time" not in FORMAT_CHECKER.checkers:  # pragma: no cover
    raise RuntimeError(
        "rfc3339-validator is required: jsonschema cannot enforce date-time without it"
    )


@dataclass(frozen=True)
class OpenAIXError:
    pointer: str
    message: str

    def __str__(self) -> str:
        return f"{self.pointer}: {self.message}"


def pointer(parts) -> str:
    """RFC 6901 JSON Pointer; the empty path is the document root ('')."""
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def schema_for(document: Any) -> dict[str, Any]:
    """Pick the schema by `$schema` (an $id), else by `kind`. Raises ValueError if neither identifies one."""
    if not isinstance(document, dict):
        raise ValueError("document must be a JSON object")  # noqa: TRY004
    declared = document.get("$schema")
    if declared is not None:
        schema = schema_for_id(declared)
        if schema is None:
            raise ValueError(f"unknown $schema: {declared!r}")
        return schema
    kind = document.get("kind")
    name = KIND_SCHEMAS.get(kind, kind)
    if name not in schemas():
        raise ValueError(
            f"cannot choose a schema: unknown kind {kind!r} and no $schema"
        )
    return schemas()[name]


def validate(document: Any) -> list[OpenAIXError]:
    """All schema errors, sorted by pointer. Empty list means valid. Unknown schema is one error at ''."""
    try:
        schema = schema_for(document)
    except ValueError as exc:
        return [OpenAIXError("", str(exc))]
    validator = Draft202012Validator(
        schema, registry=registry(), format_checker=FORMAT_CHECKER
    )
    errors = [
        OpenAIXError(pointer(e.absolute_path), e.message)
        for e in validator.iter_errors(document)
    ]
    return sorted(errors, key=lambda e: (e.pointer, e.message))
