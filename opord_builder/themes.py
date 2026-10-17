"""Named document themes: one CSS file each in `templates/themes/`, layered after the base stylesheet."""

from __future__ import annotations

from functools import cache

from opord_builder._paths import THEMES_DIR


def available() -> list[str]:
    """The theme names, sorted."""
    return sorted(p.stem for p in THEMES_DIR.glob("*.css"))


def resolve(flag: str | None, document: str | None = None) -> str | None:
    """The theme to render with: the command-line `flag`, else the document's `theme`, else None (the default look).
    Raises ValueError, naming the available themes, for one that does not exist."""
    name = flag or document
    if not name:
        return None
    names = available()
    if name not in names:
        raise ValueError(
            f"unknown theme {name!r}; available themes: {', '.join(names)}"
        )
    return name


@cache
def css(name: str) -> str:
    return (THEMES_DIR / f"{name}.css").read_text(encoding="utf-8")
