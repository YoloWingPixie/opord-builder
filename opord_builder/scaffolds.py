"""Starter files for `opord init`: a valid OPORD on first run, with `TODO:` markers to replace."""

from __future__ import annotations

from opord_builder.render import CANONICAL_ANNEXES, RESERVED_LETTERS

ANNEX = """\
# Annex {letter} - {title}
status: omitted
title: {title}
body: "TODO: {title} narrative."
"""

MAIN = """\
# yaml-language-server: $schema=https://example.invalid/replace-with-schemas/bundled/opord.schema.json
# OPORD skeleton: replace the TODO markers before distribution.
$schema: urn:openaix:schema:opord:0.2.0-draft.1
kind: opord
schema_version: 0.2.0-draft.1
meta:
  id: opord-todo
  revision: "1"
  classification: UNCLASSIFIED
issuing_headquarters: "TODO: full unit designation"
date_time: "2026-01-01T12:00:00Z"
order_number: "TODO"
operation_name: "TODO: OPERATION NAME"
time_zone: Z
mission:
  statement: "TODO: who, what (task), when, where and why (purpose)."
extensions:
  org.opord-builder.order:
    annexes:
{annexes}
"""


def files() -> dict[str, str]:
    """{relative path: text} of the starter tree."""
    letters = [letter for letter in CANONICAL_ANNEXES if letter not in RESERVED_LETTERS]
    annexes = "\n".join(
        f"      {letter}: !include annexes/annex_{letter.lower()}.yaml"
        for letter in letters
    )
    return {
        "opord.yaml": MAIN.format(annexes=annexes),
        **{
            f"annexes/annex_{letter.lower()}.yaml": ANNEX.format(
                letter=letter, title=CANONICAL_ANNEXES[letter]
            )
            for letter in letters
        },
    }
