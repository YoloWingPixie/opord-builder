"""Starter-content templates for `opord init`.

The goal is to produce a *valid* OPORD tree on first run (`opord render ...`
works immediately) that a user then iteratively edits with real content.
Placeholder values are prefixed with ``TODO:`` so a post-authoring grep
catches anything the author forgot to replace."""

from __future__ import annotations

from opord_builder.schema import CANONICAL_ANNEXES, RESERVED_LETTERS

# Main OPORD skeleton. The `!include` lines wire in the per-annex files written
# alongside it; removing an !include drops that annex entirely.
_MAIN_TEMPLATE = """\
# yaml-language-server: $schema={schema_rel}
# OPORD skeleton — replace TODO markers with real content before distribution.

header:
  classification: UNCLASSIFIED
  issuing_headquarters: "TODO: Full unit designation"
  place_of_issue: "TODO: Installation or grid"
  dtg: "TODO: 011200ZJAN26"
  operation_order_number: "TODO: e.g. 26-01"
  operation_name: "TODO: OPERATION NAME"
  author: "TODO: Name, rank, staff section"
  time_zone: "ZULU"
  references: []

mission: |
  TODO: One-sentence mission statement covering who, what (task), when, where,
  and why (purpose).

situation: {{}}

execution:
  commanders_intent:
    purpose: "TODO: Broader purpose — why the operation matters above the task."

sustainment: {{}}

command_and_signal: {{}}

annexes:
{annex_includes}

authentication: {{}}
"""

# One stub per non-reserved annex. Letter + canonical title + empty body so
# the file validates, but Status resolves to OMITTED until the author fills
# the body or typed_body.
_ANNEX_TEMPLATE = """\
# Annex {letter} — {title}
letter: {letter}
title: "{title}"
body: |
  TODO: {title} narrative or "See FRAGO" placeholder.
"""


def main_yaml(schema_rel_path: str, annex_files: list[str]) -> str:
    """Render the top-level OPORD skeleton with the given schema reference
    and a list of annex-file paths to wire in via !include."""
    includes = "\n".join(f"  - !include {p}" for p in annex_files)
    return _MAIN_TEMPLATE.format(schema_rel=schema_rel_path, annex_includes=includes)


def annex_yaml(letter: str) -> str:
    """Render a per-annex stub for ``letter`` using its canonical title."""
    return _ANNEX_TEMPLATE.format(letter=letter, title=CANONICAL_ANNEXES[letter])


def published_letters() -> list[str]:
    """Letters that get a per-annex stub file — everything except reserved."""
    return [ltr for ltr in CANONICAL_ANNEXES if ltr not in RESERVED_LETTERS]
