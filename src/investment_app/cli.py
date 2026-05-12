"""CLI entry point for the Investment Analysis MVP."""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from investment_app import __version__
from investment_app.config.settings import get_settings

app = typer.Typer(
    name="investment-app",
    help="Investment Analysis MVP — research tool.",
    add_completion=False,
)
console = Console()


@app.command()
def health() -> None:
    """Print application version and current environment."""
    settings = get_settings()
    table = Table(title="Investment App — Health Check")
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")
    table.add_row("version", __version__)
    table.add_row("environment", settings.app_env)
    table.add_row("log_level", settings.log_level)
    console.print(table)


@app.command(name="config-check")
def config_check() -> None:
    """Validate configuration and report missing required variables."""
    settings = get_settings()
    missing = settings.missing_required()

    if missing:
        console.print("[bold red]Configuration check failed.[/bold red]")
        console.print("Missing required environment variables:")
        for name in missing:
            console.print(f"  - [yellow]{name.upper()}[/yellow]")
        raise typer.Exit(code=1)

    console.print("[bold green]Configuration check passed.[/bold green]")
    console.print(f"Environment: [cyan]{settings.app_env}[/cyan]")


if __name__ == "__main__":
    app()
