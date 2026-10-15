# Writing SPINS

Write instructions in their reading order. Nest related instructions under a section or paragraph. The generator assigns all printed numbers, contents entries, table and figure captions, and citation numbers.

```yaml
kind: spins
schema_version: '0.3'
scope: standing
meta:
  id: squadron-standing
  title: Special Instructions
  revision: '1'
content:
  - kind: section
    title: Airfield procedures
    blocks:
      - kind: paragraph
        id: north-field-arrival
        lead: NORTH FIELD arrival.
        text: Coordinate your arrival with local control.
      - kind: paragraph
        text:
          - text: 'For arrival coordination, see '
          - target: north-field-arrival
          - text: '.'
```

The section becomes **1**. Its paragraphs become **1.1** and **1.2**. The link prints **Paragraph 1.1**. Insert another paragraph before the arrival procedure and the reference becomes **Paragraph 1.2** automatically. An `id` is optional unless you need to link to or amend that block. Use a descriptive name, never a printed number.

## Content

| `kind` | Required content | Use |
|---|---|---|
| `section` | `title`, `blocks` | Group related instructions; nest to any supported model depth. |
| `paragraph` | `text` | Prose, optional emphasized `lead`, and optional nested `blocks`. |
| `list` | `items` | Each item has `text` and optional `blocks`; choose a marker `style`. |
| `table` | `caption`, `columns`, `rows` | Each column has `key` and `heading`; each row supplies exactly those keys. |
| `source_table` | `caption`, `source`, `columns` | Build a table from an existing typed data source. Each column also selects a scalar `field`. |
| `figure` | `caption`, `alt`, `src` | Embed a local image. Optional `width_percent` controls its width. |
| `note` | `text` | A numbered note with an optional `heading`. |
| `reference` | `reference` | Display an entry from `meta.references`. |

A section's optional `role` is `section`, `part`, `annex`, or `appendix`. Parts use Roman numerals; annexes use letters; appendices use decimal numbers. Each starts a local hierarchy. References include the enclosing scope, such as **Part III, Paragraph 2.1**. Ordinary sections, paragraphs, and lists share a decimal sequence. Tables, figures, notes, and bibliography entries have separate document-wide counters. A table between two paragraphs does not create a gap in the paragraph numbers.

List styles are `bullet`, `decimal`, `lower_alpha`, `upper_alpha`, `lower_roman`, and `upper_roman`. Markers are automatic; `start` is optional and defaults to 1. Numbered descendants inside a list item extend the list number with the item's ordinal position. Markdown uses embedded HTML for lists so these styles and nested mixed content survive export.

## Text and references

Use a plain string for normal prose. For formatting or links, use a list of text runs:

```yaml
text:
  - text: 'Check-in. '
    marks: [bold, underline]
  - text: 'Use the channel in '
  - target: exercise-channels
  - text: '; consult '
  - citation: exercise-brief
  - text: ' for the complete briefing.'
```

Marks are `bold`, `italic`, `underline`, and `code`. Text runs preserve spaces, so quote leading or trailing spaces. A `target` links to a block's `id`. A `citation` links to an `id` in `meta.references`. The generator supplies visible reference numbers. Optional `text` on either link supplies descriptive wording when needed. Literal text is escaped; it is not interpreted as HTML.

## Reusing standing instructions

A mission document sets `scope: mission`, an effective `period` with timezone offsets, and a `base` with the standing document's `id`, exact `revision`, and relative `path`. Its `changes` can:

- `add` a `block` at the root or inside a section/paragraph identified by `parent`; optional `before` or `after` selects a sibling anchor.
- `replace` a `target` with a `block` that retains the target's `id`.
- `remove` a `target`.

Amendment targets, parents, and insertion anchors refer to baseline identifiers. Added blocks use new identifiers; replacements may retain identifiers from their own replaced subtree. Repeated additions after the same anchor retain their authored order. Conflicting writes, broken references, and mismatched baseline revisions fail validation. Mission `content` appends to the composed baseline; use an insertion amendment to put a mission part first. Numbering runs after composition. The standing source stays unchanged.

Baseline bibliography entries carry forward; conflicting definitions fail. Classification and handling carry forward when absent from the mission metadata. Presentation fields inherit unless the mission overrides them. Other mission metadata is authored on the mission document.

The existing `!include` and `variables` loader is available. Image and source-table paths resolve relative to the SPINS file that owns them, including its standing baseline. An included fragment uses its owning SPINS file's asset directory. Supported image extensions are PNG, JPEG, GIF, WebP, and SVG. HTML embeds images and CSS; PDF uses that same rendered document. Markdown image data URLs require viewer support.

## Generate and inspect

```bash
task render:spins -- examples/spins-example.yaml
task schema:spins
task docs:spins
task test:spins
```

Read the [standing source](../examples/spins-standing.yaml), [mission amendments](../examples/spins-example.yaml), [generated HTML](spins-example.html), and [complete field reader](complete-schema.html#current-SPINS). The examples are fictional DCS training content. See the [research sources](spins-sources.html) and [requirements](requirements/spins.md) for the format evidence and verification contract.

SPINS 0.3 provides publication structure rather than prescribing a mandatory chapter list. It does not validate the operational correctness of procedures or import ATO tasking. ATO remains a separate proposal in the complete field reader.
