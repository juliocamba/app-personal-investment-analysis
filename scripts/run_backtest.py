"""Historical signal-validation refresh runner.

Usage:
    python scripts/run_backtest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rich.console import Console

from investment_app.backtest import refresh_signal_backtest_observations

console = Console()


def main() -> None:
    written = refresh_signal_backtest_observations()
    console.print(
        f"[green]Signal validation refresh complete.[/green] "
        f"Wrote [bold]{written}[/bold] observation row(s)."
    )


if __name__ == "__main__":
    main()
