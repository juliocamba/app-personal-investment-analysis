"""Supabase schema validator.

Probes the connected Supabase instance and confirms all required tables exist.

Usage:
    python scripts/validate_supabase_schema.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rich.console import Console
from rich.table import Table as RichTable

from investment_app.config.settings import get_settings
from investment_app.db.schema_validator import REQUIRED_TABLES, validate_tables
from investment_app.db.supabase_client import get_supabase_client

console = Console()


def main() -> None:
    settings = get_settings()
    invalid = settings.missing_required()

    if invalid:
        console.print(
            "[bold red]Cannot validate schema: "
            "Supabase configuration is missing or placeholder-valued.[/bold red]"
        )
        for name in sorted(invalid):
            console.print(f"  - [yellow]{name.upper()}[/yellow]")
        sys.exit(1)

    console.print(f"Connecting to: [cyan]{settings.supabase_url}[/cyan]")

    try:
        client = get_supabase_client()
        present, missing = validate_tables(client)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[bold red]Connection failed:[/bold red] {exc}")
        sys.exit(1)

    result_table = RichTable(title="Schema Validation", show_lines=False)
    result_table.add_column("Table", style="cyan", no_wrap=True)
    result_table.add_column("Status")
    for name in REQUIRED_TABLES:
        status = (
            "[green]✓ present[/green]"
            if name in present
            else "[red]✗ missing[/red]"
        )
        result_table.add_row(name, status)
    console.print(result_table)

    if missing:
        console.print(
            f"[bold red]Schema validation failed. "
            f"{len(missing)} table(s) missing: {', '.join(missing)}[/bold red]"
        )
        sys.exit(1)

    console.print(
        "[bold green]Schema validation passed — all required tables present.[/bold green]"
    )


if __name__ == "__main__":
    main()
