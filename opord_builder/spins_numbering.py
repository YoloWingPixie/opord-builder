"""Publication numbering derived from the effective SPINS hierarchy."""

from collections import Counter
from dataclasses import dataclass, field

from opord_builder.renderer import letter_for
from opord_builder.schema.spins import (
    SPINS,
    ListBlock,
    Paragraph,
    ReferenceBlock,
    Section,
)

ROMAN_DIGITS = (
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
)


def _roman(number: int) -> str:
    result = []
    for value, symbol in ROMAN_DIGITS:
        count, number = divmod(number, value)
        result.append(symbol * count)
    return "".join(result)


@dataclass
class PublicationNumbering:
    labels: dict[str, str] = field(default_factory=dict)
    references: dict[str, str] = field(default_factory=dict)
    citations: dict[str, str] = field(default_factory=dict)


def number_publication(document: SPINS) -> PublicationNumbering:
    numbering = PublicationNumbering(
        citations={
            reference.id: f"Reference {index}"
            for index, reference in enumerate(document.meta.references, 1)
        }
    )
    global_counts = Counter()

    def visit(blocks, path="content", prefix="", scope=()):
        counts = Counter()
        for index, block in enumerate(blocks):
            here = f"{path}-{index}"
            child_prefix, child_scope = prefix, scope
            if isinstance(block, Section) and block.role != "section":
                counts[block.role] += 1
                number = counts[block.role]
                marker = (
                    _roman(number)
                    if block.role == "part"
                    else letter_for(number).upper()
                    if block.role == "annex"
                    else str(number)
                )
                label = f"{block.role.title()} {marker}"
                enclosing = (*scope, f"Paragraph {prefix}") if prefix else scope
                child_prefix, child_scope = "", (*enclosing, label)
                reference = ", ".join(child_scope)
            elif isinstance(block, (Section, Paragraph, ListBlock)):
                counts["paragraph"] += 1
                label = (
                    f"{prefix}.{counts['paragraph']}"
                    if prefix
                    else str(counts["paragraph"])
                )
                reference = ", ".join((*scope, f"{block.kind.title()} {label}"))
                child_prefix = label
            elif isinstance(block, ReferenceBlock):
                label = reference = numbering.citations[block.reference]
            else:
                kind = (
                    "table"
                    if block.kind in ("source_table", "openaix_table")
                    else block.kind
                )
                global_counts[kind] += 1
                label = reference = f"{kind.title()} {global_counts[kind]}"
            numbering.labels[here] = label
            if block.id:
                numbering.references[block.id] = reference
            if isinstance(block, (Section, Paragraph)):
                visit(block.blocks, here, child_prefix, child_scope)
            elif isinstance(block, ListBlock):
                for item_index, item in enumerate(block.items):
                    visit(
                        item.blocks,
                        f"{here}-item-{item_index}",
                        f"{child_prefix}.{block.start + item_index}",
                        child_scope,
                    )

    visit(document.content)
    return numbering
