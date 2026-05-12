"""YAML configuration file loader."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_CONFIG_DIR = Path(__file__).parent.parent.parent.parent / "configs"


def load_yaml(path: Path) -> Any:
    """Load and return the contents of a YAML file."""
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_watchlist(path: Path | None = None) -> dict[str, Any]:
    """Load the watchlist configuration."""
    resolved = path or _CONFIG_DIR / "watchlist.example.yml"
    return load_yaml(resolved)  # type: ignore[return-value]


def load_valuation_defaults(path: Path | None = None) -> dict[str, Any]:
    """Load the valuation defaults configuration."""
    resolved = path or _CONFIG_DIR / "valuation_defaults.yml"
    return load_yaml(resolved)  # type: ignore[return-value]


def load_scoring_weights(path: Path | None = None) -> dict[str, Any]:
    """Load the scoring weights configuration."""
    resolved = path or _CONFIG_DIR / "scoring_weights.yml"
    return load_yaml(resolved)  # type: ignore[return-value]


def load_providers(path: Path | None = None) -> dict[str, Any]:
    """Load the providers configuration."""
    resolved = path or _CONFIG_DIR / "providers.yml"
    return load_yaml(resolved)  # type: ignore[return-value]
