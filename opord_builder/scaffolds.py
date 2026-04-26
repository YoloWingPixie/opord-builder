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


def main_yaml(
    schema_rel_path: str,
    annex_files: list[str],
    data_source_block: str = "",
) -> str:
    """Render the top-level OPORD skeleton with the given schema reference
    and a list of annex-file paths to wire in via !include.

    When *data_source_block* is non-empty it is inserted between the
    ``variables:`` / header area and the ``annexes:`` section so that the
    generated OPORD references external data-source files.
    """
    includes = "\n".join(f"  - !include {p}" for p in annex_files)
    text = _MAIN_TEMPLATE.format(schema_rel=schema_rel_path, annex_includes=includes)
    if data_source_block:
        marker = "\nannexes:\n"
        if marker not in text:
            raise ValueError("Cannot locate 'annexes:' marker in main template")
        text = text.replace(marker, f"\n{data_source_block}\n\nannexes:\n")
    return text


def annex_yaml(letter: str) -> str:
    """Render a per-annex stub for ``letter`` using its canonical title."""
    return _ANNEX_TEMPLATE.format(letter=letter, title=CANONICAL_ANNEXES[letter])


def published_letters() -> list[str]:
    """Letters that get a per-annex stub file — everything except reserved."""
    return [ltr for ltr in CANONICAL_ANNEXES if ltr not in RESERVED_LETTERS]


# ---------------------------------------------------------------------------
# Standalone data-source stubs (fires / targeting)
# ---------------------------------------------------------------------------

_JPITL_TEMPLATE = """\
# yaml-language-server: $schema={schema_rel}
# Standalone JPITL — replace TODO markers with real target data.

kind: jpitl
meta:
  title: "TODO: JPITL title"
entries:
  - target_number: "TODO: TGT 0001"
    priority_rank: 1
    target_name: "TODO: Target name"
    target_description: "TODO: Target description"
    category: C2
    location: "38SMB00000000"
    component_tasked: LAND
    desired_effect: DESTROY
    engagement_guidance: "TODO: Engagement guidance"
    approval_authority: "TODO: Approval authority"
"""

_TST_TEMPLATE = """\
# yaml-language-server: $schema={schema_rel}
# Standalone TST list — replace TODO markers with real target data.

kind: tst
meta:
  title: "TODO: TST list title"
entries:
  - tst_number: "TODO: TST-01"
    priority_class: TST_1
    category: WMD
    target_description: "TODO: Target description"
    expected_activity: "TODO: Expected activity"
    pid_standard: "TODO: PID standard"
    engagement_authority: "TODO: Engagement authority"
"""

_HPT_TEMPLATE = """\
# yaml-language-server: $schema={schema_rel}
# Standalone HPT list — replace TODO markers with real target data.

kind: hpt
meta:
  title: "TODO: HPT list title"
entries:
  - priority_rank: 1
    category: C2
    target_description: "TODO: Target description"
    signature: "TODO: Observable signature"
    engagement_guidance: "TODO: Engagement guidance"
"""


def jpitl_yaml(schema_rel_path: str = "") -> str:
    """Render a starter JPITL data-source stub."""
    return _JPITL_TEMPLATE.format(schema_rel=schema_rel_path)


def tst_yaml(schema_rel_path: str = "") -> str:
    """Render a starter TST data-source stub."""
    return _TST_TEMPLATE.format(schema_rel=schema_rel_path)


def hpt_yaml(schema_rel_path: str = "") -> str:
    """Render a starter HPT data-source stub."""
    return _HPT_TEMPLATE.format(schema_rel=schema_rel_path)
