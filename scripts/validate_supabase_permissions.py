"""Supabase permission-matrix validator.

Probes the connected Supabase instance using the ``check_permission_matrix``
function (defined in 011_explicit_grants_and_rls_hardening.sql) and confirms
that the intended access-tier model is enforced.

Failures are printed with a clear summary; the script exits with code 1 when
any check fails.

Usage:
    python scripts/validate_supabase_permissions.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rich.console import Console
from rich.table import Table as RichTable

from investment_app.config.settings import get_settings
from investment_app.db.supabase_client import get_supabase_client

console = Console()


def main() -> None:
    settings = get_settings()
    invalid = settings.missing_required()

    if invalid:
        console.print(
            "[bold red]Cannot validate permissions: "
            "Supabase configuration is missing or placeholder-valued.[/bold red]"
        )
        for name in sorted(invalid):
            console.print(f"  - [yellow]{name.upper()}[/yellow]")
        sys.exit(1)

    console.print(f"Connecting to: [cyan]{settings.supabase_url}[/cyan]")

    try:
        client = get_supabase_client()
        response = client.rpc("check_permission_matrix").execute()
    except Exception as exc:  # noqa: BLE001
        console.print(f"[bold red]Connection failed:[/bold red] {exc}")
        console.print(
            "[yellow]Hint:[/yellow] ensure migration "
            "011_explicit_grants_and_rls_hardening.sql has been applied."
        )
        sys.exit(1)

    checks: list[dict] = response.data or []

    if not checks:
        console.print(
            "[bold red]check_permission_matrix() returned no data.[/bold red]\n"
            "[yellow]Hint:[/yellow] apply migration "
            "011_explicit_grants_and_rls_hardening.sql first."
        )
        sys.exit(1)

    result_table = RichTable(title="Permission Matrix Validation", show_lines=False)
    result_table.add_column("Check", style="cyan", no_wrap=True)
    result_table.add_column("Status", no_wrap=True)
    result_table.add_column("Detail")

    failed: list[str] = []

    for item in checks:
        check_name = item.get("check", "unknown")
        passed = item.get("passed", False)
        detail = item.get("detail", "")

        status_label = "[green]PASS[/green]" if passed else "[bold red]FAIL[/bold red]"
        result_table.add_row(check_name, status_label, detail)

        if not passed:
            failed.append(check_name)

    console.print(result_table)

    if failed:
        console.print(
            f"\n[bold red]Permission validation failed. "
            f"{len(failed)} check(s) did not pass: {', '.join(failed)}[/bold red]"
        )
        console.print(
            "[yellow]Run the audit queries in sql/audit/ for a full diagnosis.[/yellow]"
        )
        sys.exit(1)

    console.print(
        "\n[bold green]Permission validation passed — "
        "all checks passed.[/bold green]"
    )


if __name__ == "__main__":
    main()
