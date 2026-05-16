import React, { useEffect, useMemo, useState } from "react";
import {
  fetchPortfolioPositions,
  fetchPortfolioPositionsFxEur,
  fetchPortfolioSummary,
  fetchPortfolioSummaryFxEur,
} from "../lib/api";
import { formatPct, formatPrice } from "../lib/formatters";
import type {
  PortfolioBreakdownCount,
  PortfolioExposureItem,
  PortfolioPositionFxEurRow,
  PortfolioPositionRow,
  PortfolioSummaryFxEurRow,
  PortfolioSummaryRow,
} from "../types";

const EMPTY_SUMMARY: PortfolioSummaryRow = {
  active_position_count: 0,
  closed_position_count: 0,
  active_positions_with_price: 0,
  active_positions_missing_price: 0,
  active_positions_currency_mismatch: 0,
  computable_total_cost_basis: 0,
  computable_total_market_value: 0,
  computable_total_unrealized_gain_loss: 0,
  computable_total_unrealized_return_pct: null,
  open_review_alert_count: 0,
  critical_data_quality_count: 0,
  positions_by_signal: [],
  positions_by_thesis_confidence: [],
  company_concentration: [],
  sector_exposure: [],
  geography_exposure: [],
};

const EMPTY_FX_SUMMARY: PortfolioSummaryFxEurRow = {
  normalized_total_cost_basis_eur: 0,
  normalized_total_market_value_eur: 0,
  normalized_total_unrealized_gain_loss_eur: 0,
  normalized_total_unrealized_return_pct: null,
  positions_missing_fx_rate: 0,
  positions_fx_normalized_count: 0,
};

function formatCurrencyOrDash(value: number | null | undefined, currency = "USD"): string {
  if (value == null) return "-";
  return formatPrice(value, currency);
}

function formatPercentOrDash(value: number | null | undefined): string {
  if (value == null) return "-";
  return formatPct(value, 1);
}

function formatStatusText(value: string | null | undefined): string {
  if (!value) return "-";
  if (value === value.toUpperCase()) return value;
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function countLabel(items: PortfolioBreakdownCount[], key: "signal" | "confidence_level"): string {
  if (items.length === 0) return "None";
  return items
    .map((item) => `${formatStatusText(item[key] ?? "unknown")}: ${item.count}`)
    .join(" | ");
}

function exposureLabel(
  items: PortfolioExposureItem[],
  key: "ticker" | "sector" | "country",
): string {
  if (items.length === 0) return "No computable exposure";
  return items
    .slice(0, 5)
    .map((item) => `${item[key] ?? "Unknown"} ${formatPercentOrDash(item.weight_pct)}`)
    .join(" | ");
}

export function PortfolioPage() {
  const [summary, setSummary] = useState<PortfolioSummaryRow>(EMPTY_SUMMARY);
  const [positions, setPositions] = useState<PortfolioPositionRow[]>([]);
  const [fxSummary, setFxSummary] = useState<PortfolioSummaryFxEurRow>(EMPTY_FX_SUMMARY);
  const [fxPositions, setFxPositions] = useState<PortfolioPositionFxEurRow[]>([]);
  const [showFxEstimate, setShowFxEstimate] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetchPortfolioSummary(),
      fetchPortfolioPositions(),
      fetchPortfolioSummaryFxEur(),
      fetchPortfolioPositionsFxEur(),
    ])
      .then(([summaryRow, positionRows, fxSummaryRow, fxPositionRows]) => {
        setSummary(summaryRow);
        setPositions(positionRows);
        setFxSummary(fxSummaryRow);
        setFxPositions(fxPositionRows);
        setLoading(false);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
  }, []);

  const hasCoverageWarning =
    summary.active_positions_missing_price > 0
    || summary.active_positions_currency_mismatch > 0;
  const hasFxCoverageWarning = fxSummary.positions_missing_fx_rate > 0;
  const fxPositionsById = useMemo(
    () => new Map(fxPositions.map((position) => [position.id, position])),
    [fxPositions],
  );

  if (loading) {
    return (
      <div className="page-state" aria-live="polite" aria-busy="true">
        <div className="spinner" aria-label="Loading portfolio..." />
        <p>Loading portfolio...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-state page-state--error" role="alert">
        <p className="page-state__title">Failed to load portfolio</p>
        <p className="page-state__detail">{error}</p>
      </div>
    );
  }

  if (summary.active_position_count === 0 && summary.closed_position_count === 0) {
    return (
      <div className="page">
        <div className="page__header">
          <h1 className="page__title">Portfolio</h1>
        </div>
        <div className="page-state" aria-live="polite">
          <p className="page-state__title">No portfolio positions yet</p>
          <p className="page-state__detail">
            Add positions first to see portfolio totals, exposures, and coverage flags.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page__header">
        <h1 className="page__title">Portfolio</h1>
        <span className="page__subtitle">Display-only aggregate view from persisted position state</span>
      </div>

      {hasCoverageWarning && (
        <section className="portfolio-banner" role="status" aria-live="polite">
          <p className="portfolio-banner__title">Coverage note</p>
          <p className="portfolio-banner__text">
            Portfolio totals exclude positions with missing current prices or currency mismatches.
            No estimation or FX conversion is applied in this phase.
          </p>
        </section>
      )}

      <section className="portfolio-summary" aria-label="Portfolio summary cards">
        <article className="portfolio-card">
          <span className="portfolio-card__label">Active positions</span>
          <span className="portfolio-card__value">{summary.active_position_count}</span>
        </article>
        <article className="portfolio-card">
          <span className="portfolio-card__label">Closed positions</span>
          <span className="portfolio-card__value">{summary.closed_position_count}</span>
        </article>
        <article className="portfolio-card">
          <span className="portfolio-card__label">Computable cost basis</span>
          <span className="portfolio-card__value">
            {formatCurrencyOrDash(summary.computable_total_cost_basis)}
          </span>
        </article>
        <article className="portfolio-card">
          <span className="portfolio-card__label">Computable market value</span>
          <span className="portfolio-card__value">
            {formatCurrencyOrDash(summary.computable_total_market_value)}
          </span>
        </article>
        <article className="portfolio-card">
          <span className="portfolio-card__label">Computable unrealized P&amp;L</span>
          <span
            className={`portfolio-card__value ${
              summary.computable_total_unrealized_gain_loss > 0
                ? "num--positive"
                : summary.computable_total_unrealized_gain_loss < 0
                  ? "num--negative"
                  : ""
            }`}
          >
            {formatCurrencyOrDash(summary.computable_total_unrealized_gain_loss)}
          </span>
        </article>
        <article className="portfolio-card">
          <span className="portfolio-card__label">Computable unrealized return</span>
          <span className="portfolio-card__value">
            {formatPercentOrDash(summary.computable_total_unrealized_return_pct)}
          </span>
        </article>
        <article className="portfolio-card">
          <span className="portfolio-card__label">Open review alerts</span>
          <span className="portfolio-card__value">{summary.open_review_alert_count}</span>
        </article>
        <article className="portfolio-card">
          <span className="portfolio-card__label">Critical data-quality positions</span>
          <span className="portfolio-card__value">{summary.critical_data_quality_count}</span>
        </article>
        <article className="portfolio-card">
          <span className="portfolio-card__label">Missing current prices</span>
          <span className="portfolio-card__value">{summary.active_positions_missing_price}</span>
        </article>
        <article className="portfolio-card">
          <span className="portfolio-card__label">Currency mismatches</span>
          <span className="portfolio-card__value">{summary.active_positions_currency_mismatch}</span>
        </article>
      </section>

      <section className="portfolio-panel portfolio-panel--fx" aria-label="FX normalized portfolio estimates">
        <div className="portfolio-panel__header">
          <div>
            <h2 className="portfolio-panel__title">FX-normalized estimate (EUR)</h2>
            <p className="portfolio-panel__text">
              Uses stored ECB daily FX rates matched by exact price date only.
            </p>
          </div>
          <button
            type="button"
            className="button button--secondary"
            onClick={() => setShowFxEstimate((current) => !current)}
            aria-expanded={showFxEstimate}
          >
            {showFxEstimate ? "Hide EUR estimate" : "Show EUR estimate"}
          </button>
        </div>

        {showFxEstimate && (
          <>
            {hasFxCoverageWarning && (
              <section className="portfolio-banner" role="status" aria-live="polite">
                <p className="portfolio-banner__title">FX coverage note</p>
                <p className="portfolio-banner__text">
                  FX-normalized totals exclude rows without an exact-date stored ECB FX rate.
                </p>
              </section>
            )}

            <section className="portfolio-summary" aria-label="FX normalized summary cards">
              <article className="portfolio-card">
                <span className="portfolio-card__label">Normalized cost basis (EUR)</span>
                <span className="portfolio-card__value">
                  {formatCurrencyOrDash(fxSummary.normalized_total_cost_basis_eur, "EUR")}
                </span>
              </article>
              <article className="portfolio-card">
                <span className="portfolio-card__label">Normalized market value (EUR)</span>
                <span className="portfolio-card__value">
                  {formatCurrencyOrDash(fxSummary.normalized_total_market_value_eur, "EUR")}
                </span>
              </article>
              <article className="portfolio-card">
                <span className="portfolio-card__label">Normalized unrealized P&amp;L (EUR)</span>
                <span
                  className={`portfolio-card__value ${
                    fxSummary.normalized_total_unrealized_gain_loss_eur > 0
                      ? "num--positive"
                      : fxSummary.normalized_total_unrealized_gain_loss_eur < 0
                        ? "num--negative"
                        : ""
                  }`}
                >
                  {formatCurrencyOrDash(fxSummary.normalized_total_unrealized_gain_loss_eur, "EUR")}
                </span>
              </article>
              <article className="portfolio-card">
                <span className="portfolio-card__label">Normalized unrealized return</span>
                <span className="portfolio-card__value">
                  {formatPercentOrDash(fxSummary.normalized_total_unrealized_return_pct)}
                </span>
              </article>
              <article className="portfolio-card">
                <span className="portfolio-card__label">Rows missing FX coverage</span>
                <span className="portfolio-card__value">{fxSummary.positions_missing_fx_rate}</span>
              </article>
              <article className="portfolio-card">
                <span className="portfolio-card__label">Rows included in EUR estimate</span>
                <span className="portfolio-card__value">{fxSummary.positions_fx_normalized_count}</span>
              </article>
            </section>
          </>
        )}
      </section>

      <section className="portfolio-exposures" aria-label="Portfolio exposure sections">
        <article className="portfolio-panel">
          <h2 className="portfolio-panel__title">Positions by signal</h2>
          <p className="portfolio-panel__text">
            {countLabel(summary.positions_by_signal, "signal")}
          </p>
        </article>
        <article className="portfolio-panel">
          <h2 className="portfolio-panel__title">Positions by thesis confidence</h2>
          <p className="portfolio-panel__text">
            {countLabel(summary.positions_by_thesis_confidence, "confidence_level")}
          </p>
        </article>
        <article className="portfolio-panel">
          <h2 className="portfolio-panel__title">Concentration by company</h2>
          <p className="portfolio-panel__text">
            {exposureLabel(summary.company_concentration, "ticker")}
          </p>
        </article>
        <article className="portfolio-panel">
          <h2 className="portfolio-panel__title">Sector exposure</h2>
          <p className="portfolio-panel__text">
            {exposureLabel(summary.sector_exposure, "sector")}
          </p>
        </article>
        <article className="portfolio-panel">
          <h2 className="portfolio-panel__title">Geography exposure</h2>
          <p className="portfolio-panel__text">
            {exposureLabel(summary.geography_exposure, "country")}
          </p>
        </article>
      </section>

      <div className="table-wrapper">
        <table className="positions-table" aria-label="Portfolio positions">
          <thead>
            <tr>
              <th scope="col">Ticker</th>
              <th scope="col">Company</th>
              <th scope="col">Sector</th>
              <th scope="col">Country</th>
              <th scope="col">Status</th>
              <th scope="col">Signal</th>
              <th scope="col">Confidence</th>
              <th scope="col">Current value</th>
              {showFxEstimate && <th scope="col">Normalized value (EUR)</th>}
              <th scope="col">Weight</th>
              {showFxEstimate && <th scope="col">Normalized weight (EUR)</th>}
              <th scope="col">Review alerts</th>
              <th scope="col">Data quality</th>
              <th scope="col">Coverage flags</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((position) => {
              const flags = [];
              if (position.missing_current_price) flags.push("Missing price");
              if (position.currency_mismatch) flags.push("Currency mismatch");
              if (!position.value_computable && !position.missing_current_price && !position.currency_mismatch && position.status === "active") {
                flags.push("Not computable");
              }
              const fxPosition = fxPositionsById.get(position.id);
              return (
                <tr key={position.id}>
                  <td>{position.ticker}</td>
                  <td>{position.name}</td>
                  <td>{position.sector ?? "-"}</td>
                  <td>{position.country ?? "-"}</td>
                  <td>{formatStatusText(position.status)}</td>
                  <td>{formatStatusText(position.current_signal)}</td>
                  <td>{formatStatusText(position.thesis_confidence_level)}</td>
                  <td>{formatCurrencyOrDash(position.current_value, position.price_currency ?? position.currency)}</td>
                  {showFxEstimate && (
                    <td>{formatCurrencyOrDash(fxPosition?.normalized_current_value_eur, "EUR")}</td>
                  )}
                  <td>{formatPercentOrDash(position.position_weight_pct)}</td>
                  {showFxEstimate && (
                    <td>{formatPercentOrDash(fxPosition?.normalized_position_weight_pct)}</td>
                  )}
                  <td>
                    {position.open_review_alert_count > 0
                      ? `${position.open_review_alert_count} ${formatStatusText(position.highest_open_review_alert_severity)}`
                      : "-"}
                  </td>
                  <td>{formatStatusText(position.current_data_quality_status)}</td>
                  <td>{flags.length > 0 ? flags.join(", ") : "-"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="page__footer-note">
        Portfolio totals and exposures are display-only summaries from already stored state.
        FX-normalized values are estimates based on stored ECB daily rates and do not imply any
        trading, tax, allocation, or portfolio action recommendation.
      </p>
    </div>
  );
}
