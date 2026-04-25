# opord-builder

YAML-driven OPORD renderer. Turns a single `opord.yaml` into a clean Markdown
file and a drippy PDF. Schema tracks FM 6-0 (May 2022) Appendix D / ATP 5-0.2-1
for the 5-paragraph body and Annexes A–Z.

## Quick start

```bash
uv sync                                          # install deps into .venv
uv run opord render examples/example_full.yaml   # → example_full.{md,html,pdf}
uv run opord render examples/example_minimal.yaml --out-dir /tmp
```

## Rendered examples

Each YAML renders to all three formats. The rendered artifacts are committed
so you can preview the output before running anything.

| Example | YAML input | Markdown | HTML | PDF |
|---|---|---|---|---|
| **Full** — every field populated (IRON STRIKE, 28 pp) | [example_full.yaml](examples/example_full.yaml) | [example_full.md](examples/example_full.md) | [example_full.html](examples/example_full.html) | [example_full.pdf](examples/example_full.pdf) |
| **Minimal** — header + mission + one intent field (QUIET STEEL, 3 pp) | [example_minimal.yaml](examples/example_minimal.yaml) | [example_minimal.md](examples/example_minimal.md) | [example_minimal.html](examples/example_minimal.html) | [example_minimal.pdf](examples/example_minimal.pdf) |

The HTML outputs are **self-contained** (stylesheet inlined) — open the file
directly in any browser. The minimal example demonstrates the "no blank
sections" guarantee: empty paragraphs, subparagraphs, and cards don't render,
and subparagraph letters re-sequence around the gaps.

## Design principles

- **Schema-first.** The full OPORD structure is a Pydantic model; YAML is
  validated against it before rendering. Every section is optional except the
  header and mission paragraph.
- **No blank sections.** If a subparagraph, card, or annex has no content in
  the YAML, it does not render. Subparagraph letters re-sequence to skip gaps.
- **Doctrine-true.** Annex letters I/O/T/W/X/Y are reserved and cannot be
  assigned. Classification banners render on every page.

## CLI

```
opord render    <input.yaml> [--out-dir DIR] [--md/--no-md] [--html/--no-html] [--pdf/--no-pdf]
opord schema    [--out FILE] [--format json|yaml]       # JSON Schema (machine)
opord docs      [--out DIR]                              # full schema HTML tree
opord reference [--out FILE]                             # per-annex reference page
```

## Schema reference

The canonical schema is a JSON Schema (Draft 2020-12) generated directly
from the Pydantic models.

- **Machine:** [`schemas/opord.schema.json`](schemas/opord.schema.json) —
  committed at the repo root for anyone (IDE, CI, external tool) to consume.
- **Human (full JSON Schema tree):** [`docs/schema/index.html`](docs/schema/index.html) — browsable collapsible tree covering the whole OPORD schema. Generated with [`json-schema-for-humans`](https://github.com/coveooss/json-schema-for-humans).
- **Human (per-annex reference):** [`docs/annex_reference.html`](docs/annex_reference.html) — dedicated single-page reference with a section per annex letter (A–Z). Each section lists the typed-body fields with name, type, required/optional status, and doctrinal description. Includes a shared-types appendix (PIR, HVT, FSCM, DecisionPoint, etc.). This is the doc to read when asking "what goes in Annex D?"

### IDE integration (VS Code / JetBrains)

Both example YAMLs start with a schema-binding comment:

```yaml
# yaml-language-server: $schema=../schemas/opord.schema.json
```

With the **Red Hat YAML** extension (VS Code) or built-in YAML schema
support (JetBrains), you get autocomplete, inline validation, and hover
documentation for every field while editing your own OPORD YAML. Point
the `$schema` URI at the committed file or a raw-URL copy.

### Regenerating the schema + docs

```bash
uv run opord schema --out schemas/opord.schema.json   # regenerate JSON Schema
uv run opord docs                                     # regenerate HTML docs
```

Run both after any change to `opord_builder/schema/` (the Pydantic model package).

## Layout

- `opord_builder/schema/` — Pydantic models (core paragraphs, shared sub-types, per-annex typed bodies).
- `opord_builder/renderer.py` — YAML → model → Markdown + PDF.
- `opord_builder/cli.py` — Typer CLI.
- `opord_builder/templates/` — Jinja2 markdown + HTML, plus the stylesheet.
- `schemas/opord.schema.json` — generated JSON Schema (committed).
- `docs/schema/index.html` — generated human-readable schema docs (committed).
- `examples/example_full.yaml` — every field populated.
- `examples/example_minimal.yaml` — header + mission only; proves the
  "no blank sections" guarantee.
