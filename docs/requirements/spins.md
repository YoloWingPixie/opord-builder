# SPINS publication support

## Purpose and scope

Provide SPINS authoring and Markdown, HTML, and PDF generation in the application. Preserve the numbered publication structure observed in the researched military examples. The earlier external v0.2 proposal is not a deployed compatibility contract; this publication schema is version 0.3.

## Definitions

A block is a section, paragraph, list, table, figure, note, or bibliographic reference. A section or paragraph can contain nested blocks. An optional block identifier is a stable name for links and amendments. Printed numbers are generated from the effective document hierarchy. A mission SPINS document may amend one complete standing baseline.

## Known inputs and constraints

Use the existing Pydantic base, YAML include/variable loader, data-source registry, Jinja templates, and WeasyPrint. Preserve existing OPORD, FRAGO, and WARNO behavior. Do not add production dependencies. Keep prose as authored; do not infer a universal chapter list or operational rules.

## Requirements and acceptance criteria

| ID | Requirement | Acceptance criterion / method |
|---|---|---|
| SPINS-001 | The document shall preserve authored block order and nesting. | Render a seven-level hierarchy with interleaved block kinds; test. |
| SPINS-002 | The renderer shall generate publication numbering from the effective hierarchy. | Insertion/removal updates paragraph numbers, contents, and cross-references in HTML and Markdown; test. |
| SPINS-003 | Rich text shall preserve declared emphasis and references. | Render bold, italic, underline, code, internal links, and citations with escaped literal text; test. |
| SPINS-004 | Tables shall validate their row/column contract. | Reject missing/unknown cells and duplicate column keys; test. |
| SPINS-005 | Resource tables shall validate data through the existing registry. | Render a real typed source and reject invalid field selections; test. |
| SPINS-006 | The document shall reject duplicate identifiers and unresolved references. | Exercise nested paragraphs, cells, and notes; test. |
| SPINS-007 | A mission amendment shall pin its standing baseline revision. | Reject a wrong revision and non-standing baseline; test. |
| SPINS-008 | Composition shall retain source order and leave input objects unchanged. | Replace/add/remove nested nodes and compare both inputs before/after; test. |
| SPINS-009 | Figure paths shall resolve relative to the document that owns them. | Baseline and mission figures in different directories embed correctly; test. |
| SPINS-010 | HTML shall embed local figures and styles. | Inspect output for data URLs and absence of external stylesheets; test. |
| SPINS-011 | PDF shall provide publication headers and page numbers. | Render and inspect a multi-page document; demonstration. |
| SPINS-012 | The CLI shall expose SPINS rendering and JSON Schema export. | CLI tests and named repository tasks. |
| SPINS-013 | The schema reader shall reflect the current SPINS model. | Regenerate and check reference closure and browser links; inspection. |

## Interfaces and data

`opord spins INPUT` renders the effective document. `opord schema --document-type spins` exports its JSON Schema. `content` is an ordered block list. Authors supply hierarchy and prose, never printed labels. Sections, paragraphs, and lists share hierarchical decimal numbering. Parts use Roman numerals; annexes use letters; appendices use decimal numbers. Each part, annex, or appendix starts a local hierarchy, and cross-references include its enclosing scope. Tables, figures, notes, and bibliography entries use independent document-wide sequences. List markers follow the selected style. Numbered blocks inside a list item extend the list number with the item's ordinal position. Inline formatting uses explicit text runs, not raw HTML. `source_table` reads a standalone data-source YAML through the canonical registry. Figure paths are local files; referenced source-table and figure paths are relative to their owning SPINS document, including baseline documents.

## Out of scope and risks

This change does not integrate the ATO prototype, implement USMTF, validate operational policy, or certify DCS flight/payload behavior. It does not attempt to migrate arbitrary v0.2 typed plans automatically into prose. Canonical new examples replace that provisional SPINS representation. Markdown image data URLs depend on the consuming viewer; HTML and PDF are the portable visual outputs.

## Research and standards

The design follows the publication structures in the [NATO airspace example](https://www.airportdata.com/portals/0/docs/Flight%20Permit%20Forms/Libyan%20airspace%20SPecial%20INStructions%20-%20SPINS%20-%20Edition%204%20-%2023%20June%202011.pdf), [U.S. military example, Appendix D](https://info.publicintelligence.net/MTTP-TacticalChat.pdf#page=69), and [NATO template, Annex J](https://eda.europa.eu/docs/procurement/bi-sc_joint_personnel_recovery_joint_operational_guidelines.pdf#page=137). These historical examples establish representational needs, not current operating policy or a universal mandatory outline.

Applicable shared standards: RQM-001–007, DM-001–005/017, ARCH-002/014, FUNC-001–005/013, TEST-001–003/007/008/011/019, COMM-015–022. Completion evidence belongs in the final change report.
