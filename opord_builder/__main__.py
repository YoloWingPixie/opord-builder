"""`python -m opord_builder` entry point — delegates to the Typer CLI."""

from opord_builder.cli import app

if __name__ == "__main__":
    app()
