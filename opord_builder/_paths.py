"""Shared filesystem paths for the opord_builder package."""

from __future__ import annotations

from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR: Path = _PACKAGE_ROOT / "templates"
STYLESHEET: Path = TEMPLATES_DIR / "styles.css"
EXAMPLE_FULL_YAML: Path = _PACKAGE_ROOT.parent / "examples" / "example_full.yaml"
