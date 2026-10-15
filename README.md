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

## Weather

Weather is typed. `situation.area_of_operations.weather` holds a `summary` of the effects, a
`forecasts` list (window, wind, visibility, clouds, ceiling, temperature, altimeter,
precipitation, winds aloft, effects) and `light_data` per day. Paragraph 1 prints a forecast
table (`A2992` or `Q1013` for the altimeter, `FEW030 BKN080` for clouds) and a light table.
Free text that OpenAIX has no field for stays in the order extension under
`situation.area_of_operations.weather`; its `forecasts` list is aligned with the typed one by
position, because a forecast has no identifier. A kneeboard card gets one weather line (clouds,
visibility and surface wind of the forecast that covers the takeoff) when the card is built with
`--opord`, and a steerpoint table from the flight's route (number is `RoutePoint.number`, else
the position). A SPINS `weather` block prints the same forecast table from any document.

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
opord docs [--check]                       # generated schema docs and bundled schemas
opord reference [-o FILE]                  # per-annex reference page
opord schema [-t opord|frago|spins|ato|resources] [-o FILE]   # print the bundled schema
```

`opord export -p` takes an alias (`jpitl`, `pir`, `cap_tracks`, ...) or a JSON Pointer into the
OpenAIX document, such as `/execution/tasks_to_subordinate_units`.

## Schema docs

`opord docs` writes everything generated from the schemas, deterministically:

- `docs/complete-schema.html`: one self-contained page with a field table for every OpenAIX
  type and every extension, navigated by document kind.
- `docs/annex_reference.html`: the annexes A-Z from the OpenAIX `Annexes` definitions.
- `schemas/bundled/{opord,frago,spins,ato,resources}.schema.json`: single-file schemas with the
  OpenAIX references inlined and the extensions plugged in. Point the editor at one for completion:

  ```yaml
  # yaml-language-server: $schema=../schemas/bundled/opord.schema.json
  ```

- `schemas/extensions/spins.schema.json`: generated from the SPINS layout model. The other
  extension schemas are written by hand.

`opord docs --check` exits 1 when a generated file is stale; `task check`, `task ci` and the
tests run it.

## Breaking changes

- The Pydantic authoring YAML is gone. Every input is an OpenAIX document; the example files
  were migrated (the old `variables:` and `{{ var }}` templating and the `data_sources:`
  bindings were resolved while migrating).
- Removed commands: `validate-source`, `import-openaix`, `export-openaix` and `migrate`;
  `opord schema` now prints the bundled schema, and `opord docs` and `opord reference` write the
  new generated pages. `docs/schema/` and `schemas/opord-authoring.schema.json` are gone.
- SPINS: the `source_table` block and the data-source files are gone; use `openaix_table`.
  Migrate old files with the `opord migrate` of commit 578c021 (`git show 578c021`).
- `opord frago` has a new `--base PATH` option; without it the base comes from the FRAGO's
  `base_order_path`. A base whose revision does not match is an error.
- `opord export -p` takes JSON Pointers into the OpenAIX document instead of dotted model
  paths. The aliases are kept; `comsec` and `cross_attachments` need their annex fields.
- `opord init` scaffolds an OpenAIX `opord.yaml` plus annex stubs.
- `opord validate-openaix` accepts YAML and checks extensions.
- `opord kneeboard INPUT` reads cards from the order's `org.opord-builder.kneeboard` extension.
- Weather is typed (see Weather); the old free-text forecast fields moved into the order extension.
- FRAGO output prints whole touched paragraphs; the old sparse overlay is gone.
- Annexes print in letter order; the order in the file no longer matters.

## Layout

- `opord_builder/load.py` reads and validates documents; `order.py` loads an order and its catalogues.
- `opord_builder/render.py`, `generic.py`, `format.py`: rendering from the dicts, with small pure formatters.
- `opord_builder/frago.py`, `kneeboard.py`, `spins*.py`: FRAGO changes, kneeboard cards, SPINS.
- `opord_builder/templates/` Jinja2 templates and stylesheets; `opord_builder/openaix/vendor/` the pinned OpenAIX schemas.
- `opord_builder/docs.py` generates the schema docs; `schemas/extensions/` holds the extension schemas and `schemas/bundled/` the bundles.
- `examples/` migrated examples; `docs/` committed outputs.
