"""Data-source merge infrastructure.

Resolves ``data_sources:`` bindings declared in an OPORD YAML and injects
each source's ``entries`` into the OPORD data dict before Pydantic validation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _set_at_path(data: dict, dotted_path: str, value: Any) -> None:
    """Walk *dotted_path* into *data* and set *value* at the leaf.

    Special path segments:
    - ``annexes`` navigates into the annexes list.
    - A single uppercase letter (e.g. ``D``) finds or creates the annex
      entry with that ``letter`` in the list.
    - ``typed_body`` navigates into (or creates) the ``typed_body`` dict,
      auto-injecting the ``letter`` discriminator from the parent annex.
    """
    segments = dotted_path.split(".")
    node: Any = data
    current_letter: str | None = None

    for i, seg in enumerate(segments):
        is_leaf = i == len(segments) - 1

        if seg == "annexes":
            annexes = data.setdefault("annexes", [])
            if is_leaf:
                data["annexes"] = value
                return
            node = annexes
            continue

        if isinstance(node, list) and len(seg) == 1 and seg.isupper():
            current_letter = seg
            match = next((d for d in node if d.get("letter") == seg), None)
            if match is None:
                match = {"letter": seg}
                node.append(match)
            if is_leaf:
                if isinstance(value, dict):
                    match.update(value)
                return
            node = match
            continue

        if seg == "typed_body":
            if is_leaf:
                node["typed_body"] = value
                return
            existing = node.get("typed_body")
            if existing is None:
                existing = {}
                if current_letter:
                    existing["letter"] = current_letter
                node["typed_body"] = existing
            node = existing
            continue

        # Generic dict segment
        if is_leaf:
            existing = node.get(seg)
            if isinstance(existing, list) and isinstance(value, list):
                existing.extend(value)
            else:
                node[seg] = value
            return
        node = node.setdefault(seg, {})


def resolve_data_sources(
    data: dict,
    bindings: list,
    effective_vars: dict[str, Any],
    base_path: Path,
) -> None:
    """Load, validate, and merge each data-source binding into *data*."""
    # Deferred to avoid circular import (merge -> renderer -> schema -> ...)
    from opord_builder.renderer import _load_yaml_with_variables
    from opord_builder.schema.data_sources import DATA_SOURCE_REGISTRY

    for binding in bindings:
        source = binding.get("source")
        target = binding.get("target")
        if not source or not target:
            raise ValueError(
                f"data_sources binding must have 'source' and 'target' keys, "
                f"got: {binding!r}"
            )

        source_path = (base_path / source).resolve()

        try:
            src_data, _ = _load_yaml_with_variables(
                source_path, extra_vars=effective_vars
            )
        except FileNotFoundError:
            raise FileNotFoundError(
                f"data source file not found: {source_path}"
            ) from None

        if not isinstance(src_data, dict):
            raise ValueError(
                f"data source {source_path} must be a YAML mapping"
            )

        kind = src_data.get("kind")
        if not kind:
            raise ValueError(
                f"data source {source_path} is missing a 'kind' field"
            )

        model = DATA_SOURCE_REGISTRY.get(kind)
        if model is None:
            known = ", ".join(sorted(DATA_SOURCE_REGISTRY))
            raise ValueError(
                f"unknown data source kind {kind!r} in {source_path}; "
                f"known kinds: {known}"
            )

        model.model_validate(src_data)

        entries = src_data.get("entries", [])
        _set_at_path(data, target, entries)
