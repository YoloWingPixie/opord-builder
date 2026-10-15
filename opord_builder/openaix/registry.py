"""A referencing Registry holding every vendored OpenAIX schema, keyed by its $id. No network."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource

VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
SCHEMA_DIR = VENDOR_DIR / "schemas"


def _unavailable(uri: str):
    # Unresolved refs must fail loudly; never fetch anything.
    raise NoSuchResource(ref=uri)


@cache
def schemas() -> dict[str, dict[str, Any]]:
    """Schema name (path under schemas/ minus .schema.json, e.g. 'ato', 'measures/kb') -> schema."""
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(SCHEMA_DIR.rglob("*.schema.json")):
        name = path.relative_to(SCHEMA_DIR).as_posix().removesuffix(".schema.json")
        out[name] = json.loads(path.read_text(encoding="utf-8"))
    return out


@cache
def registry() -> Registry:
    """Built once per process."""
    return Registry(retrieve=_unavailable).with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas().values()
    )


def schema_for_id(schema_id: str) -> dict[str, Any] | None:
    return next((s for s in schemas().values() if s["$id"] == schema_id), None)
