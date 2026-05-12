"""Model backtest runner — Phase 4 placeholder.

Usage:
    python scripts/run_backtest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rich.console import Console

console = Console()


def main() -> None:
    console.print("[yellow]Backtest not yet implemented — see Phase 4.[/yellow]")


if __name__ == "__main__":
    main()
