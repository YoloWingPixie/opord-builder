"""RFC 6901 JSON Pointer: parse, escape and walk."""

from __future__ import annotations

from typing import Any

MISSING = object()


def unescape(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def tokens(pointer: str) -> list[str]:
    """The unescaped tokens of a pointer. Raises ValueError when it is not '' and does not start with '/'."""
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError(
            f"not a JSON Pointer (must be '' or start with '/'): {pointer!r}"
        )
    return [unescape(t) for t in pointer[1:].split("/")]


def resolve(document: Any, pointer: str) -> Any:
    """The value at `pointer`, or `MISSING` when a key or index is absent.

    Descending into a scalar is an error (the pointer is wrong, not the data)."""
    value = document
    walked = ""
    for token in tokens(pointer):
        if isinstance(value, dict):
            if token not in value:
                return MISSING
            value = value[token]
        elif isinstance(value, list):
            if not token.isdigit() or int(token) >= len(value):
                return MISSING
            value = value[int(token)]
        else:
            raise ValueError(  # noqa: TRY004
                f"cannot descend into {type(value).__name__} at {walked or '/'!r}"
                f" with token {token!r}"
            )
        walked += "/" + token
    return value


def at(doc: Any, pointer: str) -> Any:
    """The value at a JSON Pointer, or None."""
    for key in map(unescape, pointer.split("/")[1:]):
        try:
            doc = doc[int(key) if isinstance(doc, list) else key]
        except (KeyError, IndexError, TypeError, ValueError):
            return None
    return doc
