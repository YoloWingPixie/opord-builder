"""Shared filesystem paths for the opord_builder package."""

from __future__ import annotations

from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR: Path = _PACKAGE_ROOT / "templates"
STYLESHEET: Path = TEMPLATES_DIR / "styles.css"
THEMES_DIR: Path = TEMPLATES_DIR / "themes"
EXAMPLE_FULL_YAML: Path = _PACKAGE_ROOT.parent / "examples" / "example_full.yaml"
SPINS_DEFAULT_LAYOUT: Path = TEMPLATES_DIR / "spins-default.yaml"
# The wheel ships `schemas/` inside the package; a checkout has it at the repository root.
_SHIPPED = _PACKAGE_ROOT / "schemas"
SCHEMAS_DIR: Path = _SHIPPED if _SHIPPED.is_dir() else _PACKAGE_ROOT.parent / "schemas"
EXTENSION_SCHEMAS_DIR: Path = SCHEMAS_DIR / "extensions"
