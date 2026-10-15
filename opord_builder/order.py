"""Load an order (OPORD, FRAGO or WARNO) and everything its rendering reads."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opord_builder.frago import apply_changes, check_base, touched
from opord_builder.load import (
    KNEEBOARD,
    ORDER,
    PRINT,
    DocumentError,
    load_document,
    load_resources,
)
from opord_builder.openaix.validate import OpenAIXError


@dataclass
class Order:
    """An order as the renderer reads it: the OpenAIX document `doc` (the base with the changes applied, for a
    FRAGO), its order extension `x`, and `res`, an id lookup {catalogue: {id: record}}. `head` is the document
    whose header is printed (the FRAGO itself for a FRAGO)."""

    kind: str  # opord | frago | warno
    doc: dict
    head: dict
    res: dict[str, dict[str, Any]]
    path: Path
    base: dict | None = None
    shown: set[str] | None = None  # FRAGO: the paragraphs and annexes its changes touch
    x: dict = field(default_factory=dict)

    @property
    def print(self) -> dict:
        return self.head.get("extensions", {}).get(PRINT) or {}

    @property
    def cards(self) -> list[dict]:
        return (self.doc.get("extensions", {}).get(KNEEBOARD) or {}).get("cards", [])


def lookup(resources: dict | None, doc: dict) -> dict[str, dict[str, Any]]:
    """Catalogue -> {id: record}: the resources, and the task organization as `order_units`."""
    return {
        **((resources or {}).get("resources") or {}),
        "order_units": doc.get("task_organization") or {},
    }


def load_order(path: Path | str, base: Path | str | None = None) -> Order:
    """Read an order. A FRAGO needs its base order: `base`, else the extension's `base_order_path`."""
    path = Path(path)
    head = load_document(path)
    x = (head.get("extensions") or {}).get(ORDER) or {}
    if head["kind"] == "frago":
        if not (base or x.get("base_order_path")):
            raise DocumentError(
                path,
                [
                    OpenAIXError(
                        "/extensions", "a FRAGO needs --base, or a base_order_path"
                    )
                ],
            )
        base_path = Path(base) if base else path.parent / x["base_order_path"]
        base_doc = load_document(base_path)
        check_base(head, base_doc)
        doc = apply_changes(base_doc, head["changes"])
        res = lookup(load_resources(base_doc, base_path), doc)
        shown = touched(head["changes"])
        return Order(
            "frago",
            doc,
            head,
            res,
            path,
            base_doc,
            shown,
            doc.get("extensions", {}).get(ORDER) or {},
        )
    base_doc = None
    if x.get("base_order_path"):
        base_doc = load_document(path.parent / x["base_order_path"])
    kind = "warno" if x.get("document_kind") == "warno" else "opord"
    return Order(
        kind,
        head,
        head,
        lookup(load_resources(head, path), head),
        path,
        base_doc,
        None,
        x,
    )
