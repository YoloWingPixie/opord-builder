# opord-builder

Renders OpenAIX orders (OPORD, FRAGO, WARNO), SPINS and DCS kneeboards to
Markdown, HTML and PDF. The input is an [OpenAIX](https://github.com/YoloWingPixie/openAIX)
document written as YAML or JSON; opord-builder keeps only its print and LARP
data in `org.opord-builder.*` extensions.

## Quick start

```bash
uv sync
uv run opord render examples/example_full.yaml          # -> output/example_full.{md,html,pdf}
uv run opord render examples/example_minimal.yaml -o /tmp
uv run opord frago examples/frago_01_iron_strike.yaml   # base order from the file, or --base PATH
uv run opord warno examples/warno_standalone.yaml
uv run opord spins examples/spins-standing.yaml
uv run opord kneeboard --ato tests/fixtures/openaix/atomic-thunder/ato.json
```

## Documents

Inputs are OpenAIX documents of kind `opord`, `frago`, `spins`, `ato` and `resources`
(`.yaml`, `.yml` or `.json`). `opord validate-openaix FILE...` validates a document against
the vendored schema for its kind and then each extension against its schema, and reports
JSON Pointers.

| Extension | Holds |
|---|---|
| `org.opord-builder.print` | page furniture (the upstream `PrintExtension`) |
| `org.opord-builder.order` | paragraph content with no OpenAIX field, annex status, `document_kind: warno`, `base_order_path`, `resources_path` |
| `org.opord-builder.kneeboard` | kneeboard cards, on an order or overriding an ATO flight |
| `org.opord-builder.spins` | the SPINS publication layout tree |
| `org.opord-builder.measure` | measures with no catalogue code, and the fields of a data-source entry |

The schemas are in [`schemas/extensions/`](schemas/extensions/). If OpenAIX has a typed
field that fits, the value goes there and only the rest goes in the extension.

- An order reaches its catalogues (channels, control measures, targets) through
  `resources_ref`; the document is found at the extension's `resources_path`, or as
  `resources.yaml` beside the order.
- `!include path.yaml` splices a file into a YAML document.
- Reuse values with YAML anchors; there is no templating.
- A FRAGO is an OpenAIX `frago`: a `base_order` reference plus JSON Pointer `changes`.
  It renders every paragraph and annex that a change touches and a "No change" stub for the rest.
- A WARNO is an `opord` with `extensions["org.opord-builder.order"].document_kind: warno`.
  Paragraphs it leaves out print as "To be published".

## CLI

```
opord render   INPUT [-o DIR] [--md/--no-md] [--html/--no-html] [--pdf/--no-pdf]
opord frago    INPUT [--base PATH] [...]
opord warno    INPUT [...]
opord spins    INPUT [...]
opord kneeboard [INPUT] [--ato FILE] [--flight ID] [--resources FILE] [--opord FILE] [-o DIR]
opord export   INPUT -p ALIAS_OR_POINTER [-f pdf|html|csv] [-o FILE]
opord list-products INPUT
opord init DIR
opord watch INPUT
opord validate-openaix FILE...
```

`opord export -p` takes an alias (`jpitl`, `pir`, `cap_tracks`, ...) or a JSON Pointer into the
OpenAIX document, such as `/execution/tasks_to_subordinate_units`.

## Breaking changes

- The Pydantic authoring YAML is gone. Every input is an OpenAIX document; the example files
  were migrated (the old `variables:` and `{{ var }}` templating and the `data_sources:`
  bindings were resolved while migrating).
- Removed commands: `validate-source`, `import-openaix`, `export-openaix` and `migrate`.
  Migrate old files with the `opord migrate` of commit 578c021 (`git show 578c021`).
- `opord frago` has a new `--base PATH` option; without it the base comes from the FRAGO's
  `base_order_path`. A base whose revision does not match is an error.
- `opord export -p` takes JSON Pointers into the OpenAIX document instead of dotted model
  paths. The aliases are kept; `comsec` and `cross_attachments` need their annex fields.
- `opord init` scaffolds an OpenAIX `opord.yaml` plus annex stubs.
- `opord validate-openaix` accepts YAML and checks extensions.
- `opord kneeboard INPUT` reads cards from the order's `org.opord-builder.kneeboard` extension.
- FRAGO output prints whole touched paragraphs; the old sparse overlay is gone.
- Annexes print in letter order; the order in the file no longer matters.

## Layout

- `opord_builder/load.py` reads and validates documents; `order.py` loads an order and its catalogues.
- `opord_builder/render.py`, `generic.py`, `format.py`: rendering from the dicts, with small pure formatters.
- `opord_builder/frago.py`, `kneeboard.py`, `spins*.py`: FRAGO changes, kneeboard cards, SPINS.
- `opord_builder/templates/` Jinja2 templates and stylesheets; `opord_builder/openaix/vendor/` the pinned OpenAIX schemas.
- `schemas/extensions/` the extension schemas; `examples/` migrated examples; `docs/` committed outputs.
