"""Shared Pydantic base class for every OPORD schema model.

Kept in its own tiny module so the three schema submodules (``core``,
``shared``, ``annexes``) can all import ``_Base`` without creating a
circular dependency among themselves.
"""

from __future__ import annotations

from typing import Any, get_args

from pydantic import BaseModel, ConfigDict
from pydantic.fields import FieldInfo


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def literal_value(field: FieldInfo) -> Any:
    """Return the single value pinned by a ``Literal[X]``-typed Pydantic field.

    Used where a field's type annotation is a single-value Literal acting as
    a discriminator (e.g. ``kind: Literal["frago"]``, ``letter: Literal["A"]``).
    Raises ValueError if the annotation is not a single-value Literal so a
    future schema change that widens the Literal fails loudly instead of
    silently picking the first arg."""
    args = get_args(field.annotation)
    if len(args) != 1:
        raise ValueError(
            f"expected a single-value Literal annotation, got {field.annotation!r}"
        )
    return args[0]
