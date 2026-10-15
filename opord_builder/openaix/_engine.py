"""Shared plumbing for the OPORD <-> OpenAIX adapters: dotted model paths, JSON-pointer helpers, the lossless
`authoring` overlay and the three-way carry-through merge. No OPORD knowledge lives here."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

AUTHORING_NS = "org.opord-builder.authoring"
PRINT_NS = "org.opord-builder.print"
MISSING: Any = object()

# --------------------------------------------------------------------------- dotted model paths


def _seg(container: Any, key: str) -> Any:
    return int(key) if isinstance(container, list) else key


def get_path(d: Any, path: str, default: Any = MISSING) -> Any:
    node = d
    for key in path.split("."):
        try:
            node = node[_seg(node, key)]
        except (KeyError, IndexError, TypeError, ValueError):
            return default
    return node


def pop_path(d: Any, path: str) -> Any:
    """Remove and return the value at `path`, or MISSING. Containers left empty are kept (list items need
    their index); dict keys are removed."""
    parts = path.split(".")
    node = get_path(d, ".".join(parts[:-1])) if len(parts) > 1 else d
    if node is MISSING:
        return MISSING
    try:
        if isinstance(node, list):
            return MISSING  # list items are never popped, only their fields
        return node.pop(parts[-1])
    except (KeyError, AttributeError):
        return MISSING


def set_path(d: Any, path: str, value: Any) -> None:
    """Set `path` in a nested dict/list, creating dicts, and appending to a list when the index is its length."""
    parts = path.split(".")
    node = d
    for i, key in enumerate(parts[:-1]):
        nxt_is_index = parts[i + 1].isdigit()
        if isinstance(node, list):
            idx = int(key)
            if idx == len(node):
                node.append([] if nxt_is_index else {})
            node = node[idx]
        else:
            if key not in node or node[key] is None:
                node[key] = [] if nxt_is_index else {}
            node = node[key]
    last = parts[-1]
    if isinstance(node, list):
        idx = int(last)
        if idx == len(node):
            node.append(value)
        elif idx < len(node):
            node[idx] = value
        else:
            raise IndexError(f"{path}: list index {idx} beyond length {len(node)}")
    else:
        node[last] = value


def _path_key(path: str) -> list[tuple[int, Any]]:
    return [(0, int(p)) if p.isdigit() else (1, p) for p in path.split(".")]


def sorted_paths(paths: Any) -> list[str]:
    return sorted(paths, key=_path_key)


def flatten(
    d: Any, typed_lists: set[str], prefix: str = "", out: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Leaves of a residual model dict as {dotted path: value}. Dicts and lists of dicts are walked; every other
    value is a leaf (a list of scalars stays whole). An empty list item is a leaf `{}` unless its list was built by
    a typed codec (`typed_lists`), because the codec recreates the item."""
    out = {} if out is None else out
    if isinstance(d, dict):
        for k, v in d.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                flatten(v, typed_lists, path, out)
            elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                for i, item in enumerate(v):
                    ipath = f"{path}.{i}"
                    if item or path not in typed_lists:
                        if item:
                            flatten(item, typed_lists, ipath, out)
                        else:
                            out[ipath] = {}
            elif v in ([], {}):
                continue
            else:
                out[path] = v
    return out


# --------------------------------------------------------------------------- the authoring extension


def group_stash(stash: dict[str, Any]) -> dict[str, Any]:
    """{dotted path: value} -> {section: {dotted path: value}}. A section is the first path segment, or the first
    two for `annexes` (`annexes.3`), so a FRAGO can replace the leftovers of one paragraph or annex at a time."""
    out: dict[str, dict[str, Any]] = {}
    for key in sorted_paths(stash):
        parts = key.split(".")
        section = (
            ".".join(parts[:2])
            if parts[0] == "annexes" and len(parts) > 1
            else parts[0]
        )
        out.setdefault(section, {})[key] = stash[key]
    return out


def ungroup_stash(ext: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """(flat stash, special entries whose key starts with '@')."""
    flat: dict[str, Any] = {}
    special: dict[str, Any] = {}
    for section, group in (ext or {}).items():
        if section.startswith("@"):
            special[section] = group
        else:
            flat.update(group)
    return flat, special


# --------------------------------------------------------------------------- document pointers


def ptr_get(doc: Any, pointer: str, default: Any = MISSING) -> Any:
    node = doc
    for key in [p for p in pointer.split("/") if p]:
        key = key.replace("~1", "/").replace("~0", "~")
        try:
            node = node[int(key) if isinstance(node, list) else key]
        except (KeyError, IndexError, TypeError, ValueError):
            return default
    return node


def ptr_set(doc: dict, pointer: str, value: Any) -> None:
    keys = [p.replace("~1", "/").replace("~0", "~") for p in pointer.split("/") if p]
    node = doc
    for key in keys[:-1]:
        node = node.setdefault(key, {})
    node[keys[-1]] = value


def ptr_del(doc: dict, pointer: str) -> None:
    keys = [p.replace("~1", "/").replace("~0", "~") for p in pointer.split("/") if p]
    node = doc
    for key in keys[:-1]:
        node = node.get(key)
        if not isinstance(node, dict):
            return
    node.pop(keys[-1], None)


# --------------------------------------------------------------------------- carry-through merge


def merge_owned(carry: Any, fresh: Any, old_fresh: Any) -> Any:
    """Three-way merge for one owned subtree. `fresh` is what opord-builder writes for the current model,
    `old_fresh` what it would have written for the model as imported (`carry`'s own reading). Where the two
    agree the model did not change here, so the carried value stays byte for byte; where they differ the new
    value wins. Dict keys that opord-builder never wrote (not in `fresh` or `old_fresh`) stay from `carry`."""
    if fresh == old_fresh:
        return carry
    if (
        isinstance(fresh, dict)
        and isinstance(old_fresh, dict)
        and isinstance(carry, dict)
    ):
        out = {}
        for k in carry:
            if k in fresh or k not in old_fresh:
                out[k] = carry[k]
        for k, v in fresh.items():
            out[k] = (
                merge_owned(carry.get(k, MISSING), v, old_fresh.get(k, MISSING))
                if k in carry
                else v
            )
        return {k: v for k, v in out.items() if v is not MISSING}
    return fresh


def overlay_owned(
    carry_doc: dict, fresh_doc: dict, old_fresh_doc: dict, owned: list[str]
) -> dict:
    """Write the paths in `owned` (JSON pointers) from `fresh_doc` over a copy of `carry_doc`; see merge_owned.
    Every pointer in `owned` is a subtree root. Paths outside `owned` are left exactly as carried."""
    out = copy.deepcopy(carry_doc)
    for pointer in owned:
        fresh = ptr_get(fresh_doc, pointer)
        old = ptr_get(old_fresh_doc, pointer)
        carry = ptr_get(out, pointer)
        merged = merge_owned(carry, fresh, old)
        if merged is MISSING:
            ptr_del(out, pointer)
        elif carry is MISSING or merged is not carry:
            ptr_set(out, pointer, copy.deepcopy(merged))
    return out


@dataclass
class Ctx:
    """State of one conversion run."""

    warnings: list[str] = field(default_factory=list)
    stash: dict[str, Any] = field(default_factory=dict)
    typed_lists: set[str] = field(default_factory=set)
    doc: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, Any] = field(default_factory=dict)
    scratch: dict[str, Any] = field(default_factory=dict)

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)
