"""FRAGO changes: the diff of two order documents, and applying changes to a base order."""

from __future__ import annotations

import copy
from typing import Any

EXTENSIONS = "extensions"


class StaleBaseError(ValueError):
    """The FRAGO was written against a different revision of the base order than the one supplied."""


class FragoChangeError(ValueError):
    """A change in the FRAGO cannot be applied to the base."""


def _esc(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def _unesc(key: str) -> str:
    return key.replace("~1", "/").replace("~0", "~")


def _depth(path: tuple[str, ...]) -> int:
    """How deep a diff descends: one paragraph, or one annex, or one extension group."""
    if path[:1] == (EXTENSIONS,):
        return 4 if path[2:3] == ("annexes",) else 3
    return 2


def diff_documents(base: dict, merged: dict) -> list[tuple[str, str, Any]]:
    """[(op, pointer, value)] from `base` to `merged`, one change per paragraph or annex. Lists replace whole."""
    out: list[tuple[str, str, Any]] = []

    def pointer(path: tuple[str, ...]) -> str:
        return "/" + "/".join(_esc(x) for x in path)

    def walk(b: Any, m: Any, path: tuple[str, ...]) -> None:
        if b == m:
            return
        if len(path) < _depth(path) and isinstance(b, dict) and isinstance(m, dict):
            for k, v in m.items():
                if k in b:
                    walk(b[k], v, (*path, k))
                else:
                    out.append(("add", pointer((*path, k)), copy.deepcopy(v)))
            out.extend(("remove", pointer((*path, k)), None) for k in b if k not in m)
        else:
            out.append(("replace", pointer(path), copy.deepcopy(m)))

    walk(base, merged, ())
    return out


def order_ref(doc: dict) -> dict[str, str]:
    meta = doc.get("meta") or {}
    return {"id": meta.get("id"), "revision": meta.get("revision")}


def changes_for(base: dict, merged: dict) -> list[dict]:
    target = {"kind": "opord", **order_ref(base)}
    return [
        {
            "op": op,
            "path": path,
            "target": dict(target),
            **({"value": value} if op != "remove" else {}),
        }
        for op, path, value in diff_documents(base, merged)
    ]


def check_base(frago: dict, base: dict) -> None:
    """Raise StaleBaseError unless the FRAGO and each of its changes name this base order and revision."""
    have = order_ref(base)
    if frago["base_order"] != have:
        raise StaleBaseError(
            f"FRAGO is written against base {frago['base_order']['id']!r} revision "
            f"{frago['base_order']['revision']!r}, but the base order is {have['id']!r} revision {have['revision']!r}"
        )
    for ch in frago.get("changes", []):
        t = ch["target"]
        if t["kind"] != "opord" or {"id": t["id"], "revision": t["revision"]} != have:
            raise StaleBaseError(
                f"change {ch['path']} targets {t['kind']} {t['id']!r} revision {t['revision']!r}"
            )


def apply_changes(doc: dict, changes: list[dict]) -> dict:
    """Apply OrderChange items (add / replace / remove at a JSON Pointer) to a copy of `doc`."""
    out = copy.deepcopy(doc)
    for ch in changes:
        keys = [_unesc(k) for k in ch["path"].split("/")[1:]]
        node = out
        for k in keys[:-1]:
            try:
                node = node[int(k) if isinstance(node, list) else k]
            except (KeyError, IndexError, ValueError) as exc:
                raise FragoChangeError(
                    f"{ch['path']}: parent path not found in the base"
                ) from exc
        last, op = keys[-1], ch["op"]
        try:
            if isinstance(node, list):
                idx = len(node) if last == "-" else int(last)
                if op == "add":
                    node.insert(idx, copy.deepcopy(ch["value"]))
                elif op == "replace":
                    node[idx] = copy.deepcopy(ch["value"])
                else:
                    del node[idx]
            elif op == "remove":
                del node[last]
            elif op == "replace" and last not in node:
                raise FragoChangeError(
                    f"{ch['path']}: replace target is not in the base"
                )
            else:
                node[last] = copy.deepcopy(ch["value"])
        except (KeyError, IndexError) as exc:
            raise FragoChangeError(
                f"{ch['path']}: {op} target not found in the base"
            ) from exc
    return out


def touched(changes: list[dict]) -> set[str]:
    """The paragraphs (`situation`, `execution`, ...) and annexes (`annex:B`) that the changes touch."""
    out = set()
    for ch in changes:
        keys = [_unesc(k) for k in ch["path"].split("/")[1:]]
        if keys[0] == EXTENSIONS:
            keys = keys[2:] if keys[1].endswith(".order") else []
        if keys[:1] == ["annexes"] and len(keys) > 1:
            out.add(f"annex:{keys[1]}")
        elif keys:
            out.add(keys[0])
    return out
