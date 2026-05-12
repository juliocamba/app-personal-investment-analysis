"""Unit tests for the Phase 9A _load_live_companies authority model.

These tests import the pipeline script module directly (not via subprocess)
so they can inject mock repository modules and assert on the company-selection
logic without network access or Supabase credentials.

Phase 9A two-tier model
-----------------------
1. Non-empty watchlist result    → used immediately; list_active_companies NOT called.
2. Empty watchlist result        → returned as-is (authoritative zero); no fallback.
3. Watchlist query fails         → YAML fallback directly; list_active_companies NOT called.
4. Source label propagation      → correct label returned in each scenario.

The legacy companies.active path (list_active_companies) is intentionally
removed from the pipeline authority chain and must not be called.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "run_daily_pipeline.py"


def _load_pipeline_module() -> Any:
    """Import the pipeline script as a module object (fresh import each time)."""
    spec = importlib.util.spec_from_file_location("pipeline_script_authority", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _repo_returning(companies: list[dict]) -> MagicMock:
    """Return a repo mock where list_watchlist_active_companies returns *companies*."""
    repo = MagicMock()
    repo.list_watchlist_active_companies.return_value = companies
    return repo


def _repo_raising(exc: Exception) -> MagicMock:
    """Return a repo mock where list_watchlist_active_companies raises *exc*."""
    repo = MagicMock()
    repo.list_watchlist_active_companies.side_effect = exc
    return repo


# ── 1. Non-empty watchlist result ─────────────────────────────────────────────


def test_load_live_companies_returns_watchlist_companies_when_present() -> None:
    """Non-empty watchlist result is used; legacy list_active_companies not called."""
    mod = _load_pipeline_module()
    companies = [{"id": "c1", "ticker": "AAPL"}, {"id": "c2", "ticker": "MSFT"}]
    repo = _repo_returning(companies)

    result, source = mod._load_live_companies(repo)

    assert result == companies
    assert source == "supabase-watchlist"
    repo.list_active_companies.assert_not_called()


# ── 2. Empty watchlist result is authoritative ────────────────────────────────


def test_load_live_companies_empty_watchlist_is_authoritative() -> None:
    """Empty watchlist result MUST be returned as-is; must NOT fall back to companies.active."""
    mod = _load_pipeline_module()
    repo = _repo_returning([])  # intentional empty — all memberships removed

    result, source = mod._load_live_companies(repo)

    assert result == []
    assert source == "supabase-watchlist"
    # No legacy lookup must have been attempted.
    repo.list_active_companies.assert_not_called()


def test_load_live_companies_empty_watchlist_does_not_use_yaml_fallback() -> None:
    """Empty watchlist must not fall through to YAML even if YAML has companies."""
    mod = _load_pipeline_module()
    repo = _repo_returning([])

    # Patch the YAML loader to verify it is NOT called.
    original_yaml = mod._load_watchlist_companies
    yaml_called: list[bool] = []

    def _yaml_sentinel() -> list[dict]:
        yaml_called.append(True)
        return [{"ticker": "AAPL_YAML"}]

    mod._load_watchlist_companies = _yaml_sentinel

    try:
        result, source = mod._load_live_companies(repo)
    finally:
        mod._load_watchlist_companies = original_yaml

    assert result == []
    assert source == "supabase-watchlist"
    assert yaml_called == [], "_load_watchlist_companies must not be called on empty watchlist"


# ── 3. Watchlist query failure → YAML fallback directly (no legacy path) ──────


def test_load_live_companies_falls_back_to_yaml_on_exception() -> None:
    """If list_watchlist_active_companies raises, YAML is used directly.

    list_active_companies (companies.active) must never be called.
    """
    mod = _load_pipeline_module()
    repo = _repo_raising(RuntimeError("Supabase unreachable"))

    result, source = mod._load_live_companies(repo)

    assert source == "watchlist-fallback"
    assert isinstance(result, list)
    # companies.active must not be consulted — ever.
    repo.list_active_companies.assert_not_called()


def test_load_live_companies_list_active_companies_never_called_on_failure() -> None:
    """list_active_companies is never called regardless of exception type."""
    mod = _load_pipeline_module()
    repo = _repo_raising(ConnectionError("timeout"))

    mod._load_live_companies(repo)

    repo.list_active_companies.assert_not_called()


def test_load_live_companies_list_active_companies_never_called_on_success() -> None:
    """list_active_companies is never called on a successful (non-empty) result."""
    mod = _load_pipeline_module()
    repo = _repo_returning([{"id": "c1", "ticker": "AAPL"}])

    mod._load_live_companies(repo)

    repo.list_active_companies.assert_not_called()


# ── 4. YAML fallback source label ─────────────────────────────────────────────


def test_load_live_companies_yaml_fallback_source_label() -> None:
    """Source label is 'watchlist-fallback' when list_watchlist_active_companies fails."""
    mod = _load_pipeline_module()
    repo = _repo_raising(Exception("boom"))

    _, source = mod._load_live_companies(repo)
    assert source == "watchlist-fallback"


# ── 6. Empty watchlist means pipeline processes zero companies ────────────────


def test_pipeline_processes_zero_companies_on_empty_watchlist() -> None:
    """When watchlist is empty the full pipeline runs with zero companies and exits cleanly."""
    from typer.testing import CliRunner

    mod = _load_pipeline_module()

    # Inject a repo that returns empty watchlist (authoritative).
    repo_mock = _repo_returning([])
    repo_mock.insert_pipeline_run.return_value = {"id": "run-1"}
    repo_mock.finish_pipeline_run.return_value = None
    repo_mock.log_pipeline_event.return_value = None

    run_counts: list[int] = []

    original_live = mod._run_live_pipeline

    def _counting_pipeline(**kwargs: Any) -> dict:
        # Count how many companies were available (loaded inside _run_live_pipeline).
        # We intercept _load_live_companies instead to avoid coupling to internals.
        return {"companies_processed": 0}

    # Patch _load_live_companies to return the authoritative empty list directly.
    original_load = mod._load_live_companies

    def _empty_load(repo_module: Any) -> tuple[list, str]:
        return [], "supabase-watchlist"

    mod._load_live_companies = _empty_load

    try:
        result = mod._run_live_pipeline(
            repo_module=repo_mock,
            providers_config={"providers": {}},
            fmp=None,
            sec=None,
            ecb=None,
            gdelt=None,
            store_raw_response_fn=lambda *a, **k: None,
            normalize_prices_fn=lambda *a, **k: MagicMock(data=[]),
            normalize_statements_fn=lambda *a, **k: MagicMock(data=[]),
            normalize_news_fn=lambda *a, **k: MagicMock(data=[]),
        )
    finally:
        mod._load_live_companies = original_load

    # Pipeline must finish; companies_processed must be 0.
    assert result.get("companies_processed", 0) == 0
