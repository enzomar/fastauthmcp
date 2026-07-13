"""Ceramic CLI - command-line interface for running servers and managing auth."""

import click


@click.group()
def cli() -> None:
    """Ceramic Framework CLI."""
    ...
