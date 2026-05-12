"""Historical backfill runner — Phase 2 placeholder.

Usage:
    python scripts/run_backfill.py --ticker AAPL --start 2020-01-01
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rich.console import Console

console = Console()


def main() -> None:
    console.print("[yellow]Backfill not yet implemented — see Phase 2.[/yellow]")


if __name__ == "__main__":
    main()
