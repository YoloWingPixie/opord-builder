"""SPINS publications with automatic numbering and recursive mixed content."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    HttpUrl,
    model_validator,
)
from pydantic_core import PydanticCustomError

from opord_builder.schema._base import _Base

Text = Annotated[str, Field(min_length=1)]
BlockId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]*$")]
CitationId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]*$")]
ColumnKey = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]


def _timestamp_input(value):
    if not isinstance(value, (str, datetime)):
        raise PydanticCustomError(
            "timestamp_type", "use a date/time with an explicit UTC offset"
        )
    return value


Timestamp = Annotated[AwareDatetime, BeforeValidator(_timestamp_input)]


class ClassificationLevel(str, Enum):
    """Classification markings permitted on a banner."""

    UNCLASSIFIED = "UNCLASSIFIED"
    CUI = "CUI"
    CONFIDENTIAL = "CONFIDENTIAL"
    SECRET = "SECRET"
    TOP_SECRET = "TOP SECRET"


class PublicationReference(_Base):
    id: CitationId
    title: Text
    author: Text | None = None
    date: Text | None = None
    locator: Text | None = None
    url: HttpUrl | None = None


class PublicationMetadata(_Base):
    id: BlockId
    title: Text
    revision: Text
    operation: Text | None = None
    issuing_unit: Text | None = None
    author: Text | None = None
    issued_at: Timestamp | None = None
    classification: ClassificationLevel | None = None
    handling: Text | None = None
    references: list[PublicationReference] = Field(default_factory=list)
    distribution: list[Text] = Field(default_factory=list)


class PublicationPeriod(_Base):
    start: Timestamp
    end: Timestamp

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("period.end must be later than period.start")
        return self


class PinnedPublication(_Base):
    id: BlockId
    revision: Text
    path: Text


class Presentation(_Base):
    font: Literal["serif", "sans", "monospace"] = "serif"
    text_case: Literal["preserve", "uppercase"] = "preserve"
    page_size: Literal["A4", "Letter"] = "A4"
    contents: bool = True


class TextRun(_Base):
    """Inline text preserves spaces between adjacent runs."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    text: Annotated[str, Field(min_length=1)]
    marks: list[Literal["bold", "italic", "underline", "code"]] = Field(
        default_factory=list
    )


class CrossReference(_Base):
    target: BlockId
    text: Text | None = None


class Citation(_Base):
    citation: CitationId
    text: Text | None = None


Inline = TextRun | CrossReference | Citation
RichText = str | Annotated[list[Inline], Field(min_length=1)]


def text_present(value: RichText) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return any(not isinstance(run, TextRun) or run.text.strip() for run in value)


class AnchoredBlock(_Base):
    id: BlockId | None = Field(
        default=None,
        description="Stable name for links or amendments; printed numbers are automatic.",
    )


class Section(AnchoredBlock):
    """A titled container. Part, annex, and appendix roles start a numbering scope."""

    kind: Literal["section"]
    role: Literal["part", "section", "annex", "appendix"] = "section"
    title: Text
    blocks: list[Block] = Field(min_length=1)


class Paragraph(AnchoredBlock):
    kind: Literal["paragraph"]
    lead: RichText | None = None
    text: RichText
    blocks: list[Block] = Field(default_factory=list)

    @model_validator(mode="after")
    def meaningful(self):
        if not text_present(self.text):
            raise ValueError("paragraph text cannot be blank")
        return self


class ListItem(_Base):
    text: RichText
    blocks: list[Block] = Field(default_factory=list)


class ListBlock(AnchoredBlock):
    kind: Literal["list"]
    style: Literal[
        "bullet", "decimal", "lower_alpha", "upper_alpha", "lower_roman", "upper_roman"
    ] = "bullet"
    start: Annotated[int, Field(ge=1)] = 1
    items: list[ListItem] = Field(min_length=1)


class TableColumn(_Base):
    key: ColumnKey
    heading: Text
    align: Literal["left", "center", "right"] = "left"


class TableBlock(AnchoredBlock):
    kind: Literal["table"]
    caption: Text
    columns: list[TableColumn] = Field(min_length=1)
    rows: list[dict[ColumnKey, RichText]] = Field(min_length=1)

    @model_validator(mode="after")
    def column_contract(self):
        keys = {column.key for column in self.columns}
        if len(keys) != len(self.columns):
            raise ValueError("table column keys must be unique")
        for index, row in enumerate(self.rows):
            if set(row) != keys:
                raise ValueError(
                    f"table row {index + 1}: expected cells {sorted(keys)}, got {sorted(row)}"
                )
        return self


class SourceColumn(TableColumn):
    field: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]


class SourceTableBlock(AnchoredBlock):
    kind: Literal["source_table"]
    caption: Text
    source: Text = Field(
        description="Local standalone data-source YAML, relative to the owning SPINS file."
    )
    columns: list[SourceColumn] = Field(min_length=1)


JsonPointer = Annotated[
    str,
    Field(
        pattern=r"^(/([^/~]|~[01])*)*$",
        description="RFC 6901 JSON Pointer; the empty string is the document root.",
    ),
]
RelativePointer = Annotated[
    str,
    Field(
        pattern=r"^(#key|(/([^/~]|~[01])*)*)$",
        description="JSON Pointer relative to the row; '' is the row itself and '#key' is the map key.",
    ),
]


class OpenAIXColumn(TableColumn):
    field: RelativePointer
    lookup: Text | None = Field(
        default=None,
        description="Replace identifiers by the named record: 'airfield' or '<source>:<pointer to a map keyed by id>'.",
    )


class OpenAIXTableBlock(AnchoredBlock):
    """A table built from typed OpenAIX data named by the document's `openaix` references."""

    kind: Literal["openaix_table"]
    caption: Text
    source: Literal["ato", "aco", "spins", "resources", "airfield"]
    pointer: JsonPointer = Field(
        description="Where in the source document the rows are: an array (one row per item), or an object (one row)."
    )
    columns: list[OpenAIXColumn] = Field(min_length=1)
    rows: Literal["auto", "items", "entries", "single"] = Field(
        default="auto",
        description="auto: array items, or one row for an object. entries: one row per value of a map (use field '#key' for its key).",
    )
    require: list[RelativePointer] = Field(
        default_factory=list,
        description="Drop rows in which any of these relative pointers is absent or empty.",
    )
    empty: Literal["error", "skip", "notice"] = Field(
        default="error",
        description="When no rows result: raise an error, drop the block (and any section left empty), or print a 'not provided' note.",
    )

    @model_validator(mode="after")
    def column_keys(self):
        keys = [column.key for column in self.columns]
        if len(set(keys)) != len(keys):
            raise ValueError("table column keys must be unique")
        return self


class SpinsOpenAIXRefs(_Base):
    """OpenAIX files (relative to this document) that `openaix_table` blocks read."""

    ato: Text | None = Field(
        default=None, description="Path to an OpenAIX ATO document."
    )
    aco: Text | None = Field(
        default=None, description="Path to an OpenAIX ACO document."
    )
    resources: Text | None = Field(
        default=None, description="Path to an OpenAIX resources document."
    )
    spins: Text | None = Field(
        default=None, description="Path to an OpenAIX SPINS document."
    )

    airfields: list[Text] = Field(
        default_factory=list,
        description="Paths to OpenAIX airfield, FARP or carrier records (source 'airfield').",
    )


class FigureBlock(AnchoredBlock):
    kind: Literal["figure"]
    caption: Text
    alt: Text
    src: Text = Field(
        description="Local PNG, JPEG, GIF, WebP, or SVG, relative to the owning SPINS file."
    )
    width_percent: Annotated[int, Field(ge=1, le=100)] = 100


class NoteBlock(AnchoredBlock):
    kind: Literal["note"]
    heading: Text = "NOTE"
    text: RichText

    @model_validator(mode="after")
    def meaningful(self):
        if not text_present(self.text):
            raise ValueError("note text cannot be blank")
        return self


class ReferenceBlock(AnchoredBlock):
    kind: Literal["reference"]
    reference: CitationId


Block = Annotated[
    Section
    | Paragraph
    | ListBlock
    | TableBlock
    | SourceTableBlock
    | OpenAIXTableBlock
    | FigureBlock
    | NoteBlock
    | ReferenceBlock,
    Field(discriminator="kind"),
]


class AddBlock(_Base):
    op: Literal["add"]
    parent: BlockId | None = Field(
        default=None,
        description="Section/paragraph container; omitted means document root.",
    )
    after: BlockId | None = Field(
        default=None, description="Sibling after which to insert; omitted means append."
    )
    block: Block
    before: BlockId | None = Field(
        default=None,
        description="Sibling before which to insert; mutually exclusive with after.",
    )

    @model_validator(mode="after")
    def one_position(self):
        if self.before and self.after:
            raise ValueError("choose before or after, not both")
        return self


class ReplaceBlock(_Base):
    op: Literal["replace"]
    target: BlockId
    block: Block


class RemoveBlock(_Base):
    op: Literal["remove"]
    target: BlockId


BlockChange = Annotated[
    AddBlock | ReplaceBlock | RemoveBlock, Field(discriminator="op")
]


def iter_blocks(
    blocks: list[Block], path: str = "content"
) -> Iterator[tuple[str, Block]]:
    for index, block in enumerate(blocks):
        here = f"{path}-{index}"
        yield here, block
        if isinstance(block, (Section, Paragraph)):
            yield from iter_blocks(block.blocks, here)
        elif isinstance(block, ListBlock):
            for item_index, item in enumerate(block.items):
                yield from iter_blocks(item.blocks, f"{here}-item-{item_index}")


def iter_values(value):
    if isinstance(value, BaseModel):
        yield value
        for name in type(value).model_fields:
            yield from iter_values(getattr(value, name))
    elif isinstance(value, dict):
        for child in value.values():
            yield from iter_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_values(child)


class SPINS(_Base):
    """Ordered publication blocks with automatic numbering and optional standing amendments."""

    kind: Literal["spins"]
    schema_version: Literal["0.3"]
    meta: PublicationMetadata
    scope: Literal["standing", "mission"]
    period: PublicationPeriod | None = None
    presentation: Presentation = Field(default_factory=Presentation)
    openaix: SpinsOpenAIXRefs | None = Field(
        default=None,
        description="OpenAIX files that `openaix_table` blocks read, relative to this YAML.",
    )
    content: list[Block] = Field(
        default_factory=list,
        description="Instructions in reading order. Numbering follows the effective hierarchy after amendments.",
    )
    base: PinnedPublication | None = None
    changes: list[BlockChange] = Field(default_factory=list)

    @model_validator(mode="after")
    def publication_contract(self):
        if self.scope == "mission" and self.period is None:
            raise ValueError("mission SPINS requires an effective period")
        if self.scope == "standing" and (self.base or self.changes):
            raise ValueError("standing SPINS must be a complete baseline")
        if self.changes and self.base is None:
            raise ValueError("SPINS amendments require a pinned baseline")
        if not self.content and self.base is None:
            raise ValueError("SPINS requires content or a standing baseline")
        ids = [block.id for _, block in iter_blocks(self.content) if block.id]
        if len(set(ids)) != len(ids):
            raise ValueError(
                "block identifiers must be unique throughout the publication"
            )
        references = [reference.id for reference in self.meta.references]
        if len(set(references)) != len(references):
            raise ValueError("publication reference identifiers must be unique")
        if self.base is None:
            for value in iter_values(self.content):
                if isinstance(value, CrossReference) and value.target not in ids:
                    raise ValueError(f"unresolved block reference {value.target!r}")
                key = (
                    value.citation
                    if isinstance(value, Citation)
                    else value.reference
                    if isinstance(value, ReferenceBlock)
                    else None
                )
                if key and key not in references:
                    raise ValueError(f"unresolved citation {key!r}")
        return self


for _model in (Section, Paragraph, ListItem, ListBlock, AddBlock, ReplaceBlock, SPINS):
    _model.model_rebuild()


class SpinsMetaExtra(_Base):
    """What OpenAIX `Metadata` cannot hold of a publication's metadata; the rest sits in the typed `meta`."""

    handling: Text | None = None
    references: list[PublicationReference] = Field(
        default_factory=list,
        description="Cited sources; their author, date, locator and URL have no typed home in OpenAIX.",
    )


class SpinsLayout(_Base):
    """The `org.opord-builder.spins` extension at the top level of a native OpenAIX `spins` document: the publication
    layout tree. Identification, scope, period and the pinned baseline are typed OpenAIX fields, not part of it."""

    meta: SpinsMetaExtra | None = None
    presentation: Presentation = Field(default_factory=Presentation)
    sidecars: SpinsOpenAIXRefs | None = Field(
        default=None,
        description="OpenAIX files that `openaix_table` blocks read, relative to this document.",
    )
    content: list[Block] = Field(
        default_factory=list,
        description="Instructions in reading order. Numbering follows the effective hierarchy after amendments.",
    )
    changes: list[BlockChange] = Field(
        default_factory=list,
        description="Block-level amendments to the pinned baseline (`base`).",
    )


def _dispatch(node):
    """Rewrite each discriminated `oneOf` as an `if/then` per tag, so an error names the field and not the block."""
    if isinstance(node, list):
        return [_dispatch(n) for n in node]
    if not isinstance(node, dict):
        return node
    node = {k: _dispatch(v) for k, v in node.items()}
    disc = node.pop("discriminator", None)
    if disc is None or "oneOf" not in node:
        return node
    tag, mapping = disc["propertyName"], disc["mapping"]
    del node["oneOf"]
    node.update(
        type="object",
        required=[tag],
        properties={tag: {"enum": list(mapping)}},
        allOf=[
            {"if": {"properties": {tag: {"const": value}}}, "then": {"$ref": ref}}
            for value, ref in mapping.items()
        ],
    )
    return node


def spins_extension_schema() -> dict:
    """JSON Schema 2020-12 of the `org.opord-builder.spins` extension, generated from `SpinsLayout`."""
    schema = _dispatch(SpinsLayout.model_json_schema())
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:opord-builder:extension:spins:1",
        "title": "SPINS extension",
        "description": "The `org.opord-builder.spins` extension of an OpenAIX `spins` document: the publication layout tree.",
        **{k: v for k, v in schema.items() if k not in ("title", "description")},
    }


SpinsLayout.model_rebuild()
