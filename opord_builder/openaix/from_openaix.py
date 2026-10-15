"""OpenAIX `opord` (+ optional `resources`) -> Pydantic OPORD. The inverse of `to_openaix`; see its module
docstring for what is typed and what lives in the authoring overlay."""

from __future__ import annotations

import copy
from typing import Any

from opord_builder.openaix import _mapping as mp
from opord_builder.openaix._engine import Ctx
from opord_builder.openaix.validate import validate
from opord_builder.schema.core import OPORD

PLACEHOLDER = "(not stated in the OpenAIX document)"


class OpenAIXImportError(ValueError):
    pass


def from_openaix(
    doc: dict[str, Any],
    resources: dict[str, Any] | None = None,
    jiptl: dict[str, Any] | None = None,
    *,
    carry: bool = True,
    check: bool = True,
) -> tuple[OPORD, list[str]]:
    """(model, warnings). With `carry`, the original documents are kept in `model.openaix_source` so a later
    export keeps the typed fields this model does not hold."""
    if not isinstance(doc, dict) or doc.get("kind") != "opord":
        raise OpenAIXImportError("not an OpenAIX opord document (kind must be 'opord')")
    if check:
        errors = validate(doc)
        if errors:
            raise OpenAIXImportError(
                "input does not validate against the vendored schema:\n"
                + "\n".join(f"  {e}" for e in errors[:20])
            )
    ctx = Ctx()
    d = mp.decode(doc, resources, ctx, jiptl)
    _complete(d, ctx)
    model = OPORD.model_validate(d)
    if carry:
        model = model.model_copy(
            update={
                "openaix_source": copy.deepcopy(
                    {
                        "opord": doc,
                        **({"resources": resources} if resources else {}),
                        **({"jiptl": jiptl} if jiptl else {}),
                    }
                )
            }
        )
    return model, ctx.warnings


def _complete(d: dict[str, Any], ctx: Ctx) -> None:
    """Fill required authoring fields the document does not give. A classification or a DTG is never invented."""
    h = d.setdefault("header", {})
    for key, label in (("classification", "meta.classification"), ("dtg", "date_time")):
        if key not in h:
            raise OpenAIXImportError(
                f"the document has no {label}; the authoring model requires it"
            )
    for key in (
        "issuing_headquarters",
        "place_of_issue",
        "operation_order_number",
        "operation_name",
    ):
        if key not in h:
            h[key] = PLACEHOLDER
            ctx.warn(f"header.{key}: not in the document, set to a placeholder")
    if "time_zone" not in h:
        h["time_zone"] = "ZULU"
        ctx.warn("header.time_zone: not in the document, set to ZULU")
