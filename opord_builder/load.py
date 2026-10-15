"""Read an OpenAIX document from YAML or JSON and validate it, `org.opord-builder.*` extensions included."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from opord_builder._paths import EXTENSION_SCHEMAS_DIR
from opord_builder.openaix.registry import schemas
from opord_builder.openaix.validate import (
    FORMAT_CHECKER,
    OpenAIXError,
    pointer,
    validate,
)

NS = "org.opord-builder."
ORDER, PRINT, KNEEBOARD, SPINS, MEASURE = (
    NS + n for n in ("order", "print", "kneeboard", "spins", "measure")
)
MAX_INCLUDE_DEPTH = 16


class DocumentError(ValueError):
    """A document that cannot be read or does not validate; `errors` carries JSON Pointers."""

    def __init__(self, path: Path | str, errors: list[OpenAIXError]):
        self.errors = errors
        lines = "\n".join(f"  {e.pointer or '/'}: {e.message}" for e in errors[:20])
        more = f"\n  ... and {len(errors) - 20} more" if len(errors) > 20 else ""
        super().__init__(f"{path}:\n{lines}{more}")


# --------------------------------------------------------------------------- reading


class _Loader(yaml.SafeLoader):
    """SafeLoader with `!include <path>` (relative to the including file) and timestamps kept as text."""

    stack: tuple[Path, ...] = ()


def _include(loader: _Loader, node: yaml.Node) -> Any:
    target = (loader.stack[-1].parent / loader.construct_scalar(node)).resolve()
    if target in loader.stack:
        raise ValueError(
            f"!include cycle: {' -> '.join(map(str, (*loader.stack, target)))}"
        )
    if len(loader.stack) >= MAX_INCLUDE_DEPTH:
        raise ValueError(
            f"!include nests deeper than {MAX_INCLUDE_DEPTH} levels at {target}"
        )
    return read(target, (*loader.stack, target))


_Loader.add_constructor("!include", _include)
_Loader.add_constructor(
    "tag:yaml.org,2002:timestamp", lambda loader, node: loader.construct_scalar(node)
)


def read(path: Path | str, stack: tuple[Path, ...] = ()) -> Any:
    """Parse a YAML or JSON file, resolving `!include`."""
    path = Path(path).resolve()
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    loader = _Loader(text)
    loader.stack = stack or (path,)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


# --------------------------------------------------------------------------- validation


@cache
def extension_validators() -> dict[str, Draft202012Validator]:
    """Namespace -> validator for each extension schema; built once per process."""
    out = {}
    for path in sorted(EXTENSION_SCHEMAS_DIR.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        out[NS + path.name.removesuffix(".schema.json")] = Draft202012Validator(
            schema, format_checker=FORMAT_CHECKER
        )
    return out


@cache
def schema_index() -> dict[str, dict[str, Any]]:
    """`$id` -> schema, for the vendored OpenAIX schemas and the extension schemas."""
    index = {s["$id"]: s for s in schemas().values()}
    for path in sorted(EXTENSION_SCHEMAS_DIR.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        index[schema["$id"]] = schema
    return index


def ext_schema(name: str) -> dict[str, Any]:
    return schema_index()[f"urn:opord-builder:extension:{name}:1"]


def check_extensions(doc: dict[str, Any], base: tuple = ()) -> list[OpenAIXError]:
    """Validate the `org.opord-builder.*` groups of `doc.extensions`, and those on ATO flights and control measures."""
    errors = []
    validators = extension_validators()
    for ns, value in (doc.get("extensions") or {}).items():
        if not ns.startswith(NS) or ns in (PRINT, NS + "authoring"):
            continue  # the print group belongs to the vendored schemas; `authoring` is the old stash
        at = (*base, "extensions", ns)
        if ns not in validators:
            errors.append(
                OpenAIXError(pointer(at), f"unknown opord-builder extension {ns!r}")
            )
            continue
        errors += [
            OpenAIXError(pointer((*at, *e.absolute_path)), e.message)
            for e in validators[ns].iter_errors(value)
        ]
    for cid, measure in (
        (doc.get("resources") or {}).get("control_measures") or {}
    ).items():
        errors += check_extensions(
            measure, (*base, "resources", "control_measures", cid)
        )
    for i, mission in enumerate(doc.get("missions") or []):
        for j, flight in enumerate(mission.get("flights") or []):
            errors += check_extensions(flight, (*base, "missions", i, "flights", j))
    return errors


def validate_document(doc: Any) -> list[OpenAIXError]:
    """Schema errors of the document for its kind, then of its extensions, sorted by pointer."""
    errors = validate(doc)
    if isinstance(doc, dict):
        errors += check_extensions(doc)
    return sorted(errors, key=lambda e: (e.pointer, e.message))


def load_document(path: Path | str) -> dict[str, Any]:
    """Read and validate one OpenAIX document. Raises DocumentError (JSON Pointers) when it does not validate."""
    try:
        doc = read(path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise DocumentError(path, [OpenAIXError("", str(exc))]) from exc
    if errors := validate_document(doc):
        raise DocumentError(path, errors)
    return doc


def load_resources(doc: dict, path: Path | str) -> dict | None:
    """The resources document an order reaches through `resources_ref`, found by the order extension's
    `resources_path` or else as `resources.{yaml,yml,json}` beside it. Its id and revision must match the reference."""
    ref = doc.get("resources_ref")
    if not ref:
        return None
    here = Path(path).resolve().parent
    named = (doc.get("extensions", {}).get(ORDER) or {}).get("resources_path")
    found = next(
        (
            p
            for p in (
                [here / named]
                if named
                else [here / f"resources.{e}" for e in ("yaml", "yml", "json")]
            )
            if p.is_file()
        ),
        None,
    )
    if found is None:
        raise DocumentError(
            path,
            [
                OpenAIXError(
                    "/resources_ref", f"no resources document for {ref['id']!r}"
                )
            ],
        )
    res = load_document(found)
    meta = res.get("meta", {})
    if (meta.get("id"), meta.get("revision")) != (ref["id"], ref["revision"]):
        raise DocumentError(
            path,
            [
                OpenAIXError(
                    "/resources_ref",
                    f"{found.name} is {meta.get('id')!r} revision {meta.get('revision')!r}",
                )
            ],
        )
    return res


def at(doc: Any, pointer: str) -> Any:
    """The value at a JSON Pointer, or None."""
    for key in (
        k.replace("~1", "/").replace("~0", "~") for k in pointer.split("/")[1:]
    ):
        try:
            doc = doc[int(key) if isinstance(doc, list) else key]
        except (KeyError, IndexError, TypeError, ValueError):
            return None
    return doc
