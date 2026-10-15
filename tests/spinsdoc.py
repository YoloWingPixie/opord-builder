"""Test helper: wrap a SPINS layout dict into a native OpenAIX `spins` document."""

TYPED_META = (
    "id",
    "title",
    "revision",
    "operation",
    "issuing_unit",
    "author",
    "issued_at",
    "classification",
    "distribution",
)
LAYOUT = {
    "presentation": "presentation",
    "openaix": "sidecars",
    "content": "content",
    "changes": "changes",
}


def native(data: dict) -> dict:
    """`data` has the SPINS model's keys (`openaix` for the sidecar files); the result validates as OpenAIX."""
    meta = data["meta"]
    layout = {new: data[old] for old, new in LAYOUT.items() if old in data}
    if extra := {k: meta[k] for k in ("handling", "references") if k in meta}:
        layout["meta"] = extra
    return {
        "kind": "spins",
        "schema_version": "0.2.0-draft.1",
        "scope": data["scope"],
        "meta": {k: meta[k] for k in TYPED_META if k in meta},
        **{k: data[k] for k in ("period", "base") if k in data},
        "extensions": {"org.opord-builder.spins": layout},
    }
