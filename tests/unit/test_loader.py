"""Unit tests for the YAML config loader."""
from __future__ import annotations

from pathlib import Path

import pytest

from investment_app.config.loader import (
    load_providers,
    load_scoring_weights,
    load_valuation_defaults,
    load_watchlist,
)


def test_load_watchlist_structure(configs_dir: Path) -> None:
    data = load_watchlist(configs_dir / "watchlist.example.yml")
    assert "companies" in data
    companies = data["companies"]
    assert len(companies) >= 1


def test_load_watchlist_company_fields(configs_dir: Path) -> None:
    data = load_watchlist(configs_dir / "watchlist.example.yml")
    first = data["companies"][0]
    for field in ("ticker", "name", "exchange", "country", "currency", "active"):
        assert field in first, f"Expected field '{field}' in company entry"


def test_load_valuation_defaults_structure(configs_dir: Path) -> None:
    data = load_valuation_defaults(configs_dir / "valuation_defaults.yml")
    assert "defaults" in data
    defaults = data["defaults"]
    assert "explicit_forecast_years" in defaults
    assert "terminal_growth_floor" in defaults
    assert "terminal_growth_cap" in defaults
    assert "scenario_weights" in defaults


def test_load_valuation_scenario_weights_sum(configs_dir: Path) -> None:
    data = load_valuation_defaults(configs_dir / "valuation_defaults.yml")
    weights = data["defaults"]["scenario_weights"]
    total = sum(weights.values())
    assert abs(total - 1.0) < 1e-9


def test_load_scoring_weights_structure(configs_dir: Path) -> None:
    data = load_scoring_weights(configs_dir / "scoring_weights.yml")
    assert "rule_score_weights" in data
    assert "qualitative_weights" in data


def test_load_scoring_rule_weights_sum(configs_dir: Path) -> None:
    data = load_scoring_weights(configs_dir / "scoring_weights.yml")
    weights = data["rule_score_weights"]
    total = sum(weights.values())
    assert abs(total - 1.0) < 1e-9


def test_load_providers_structure(configs_dir: Path) -> None:
    data = load_providers(configs_dir / "providers.yml")
    assert "providers" in data
    providers = data["providers"]
    assert "fmp" in providers
    assert "sec_edgar" in providers


def test_load_yaml_file_not_found(tmp_path: Path) -> None:
    from investment_app.config.loader import load_yaml

    with pytest.raises(FileNotFoundError):
        load_yaml(tmp_path / "nonexistent.yml")
