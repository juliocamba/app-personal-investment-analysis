# 04 — Phase 0: Project Bootstrap

## Objective

Create the initial repository, Python package, configuration files, local development setup, and CI-ready command structure.

## Scope

This phase does not connect to external APIs yet. It creates the foundation for the rest of the project.

## Agent instructions

Implement only this phase. Do not implement data ingestion, valuation, scoring, alerts, or frontend yet.

## Tasks

### 1. Create repository structure

Create the structure defined in `02_REPOSITORY_STRUCTURE.md`.

Minimum folders:

```text
configs/
src/investment_app/
scripts/
tests/unit/
tests/integration/
sql/
frontend/
.github/workflows/
```

### 2. Create Python project files

Create:

- `pyproject.toml`
- `requirements.txt`
- `.env.example`
- `.gitignore`
- `README.md`

### 3. Create configuration loader

Implement:

- `src/investment_app/config/settings.py`
- `src/investment_app/config/loader.py`

Requirements:

- load environment variables from `.env` locally;
- validate required settings with Pydantic;
- support `APP_ENV=local|ci|production`;
- avoid printing secrets in logs.

### 4. Create CLI entrypoint

Implement `src/investment_app/cli.py` using Typer.

Commands:

```bash
investment-app health
investment-app config-check
```

Expected behaviour:

- `health` prints app version and environment;
- `config-check` validates configuration and reports missing required variables without revealing secret values.

### 5. Create scripts

Create:

- `scripts/run_daily_pipeline.py`
- `scripts/validate_supabase_schema.py`

For Phase 0, these scripts can be placeholders that call the config loader and print a structured message.

### 6. Add tests

Add tests for:

- settings load correctly from environment;
- missing required variables are reported;
- CLI health command works.

## Acceptance criteria

- `pip install -e .` succeeds.
- `investment-app health` succeeds.
- `investment-app config-check` fails gracefully when required variables are missing.
- `pytest` passes.
- No secrets are committed.

## Suggested commit message

```text
chore: bootstrap investment analysis MVP project
```
