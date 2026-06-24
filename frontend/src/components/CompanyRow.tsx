import React, { useState } from "react";
import type { WatchlistRow } from "../types";
import { SignalBadge } from "./SignalBadge";
import { ReadinessBadge } from "./ReadinessBadge";
import { FreshnessTag } from "./FreshnessTag";
import { RedFlagList } from "./RedFlagList";
import {
  formatQualityCode,
  ResearchQualityBadge,
  researchQualityLabel,
} from "./ResearchQualityBadge";
import { formatReasonCode, readinessLabel } from "../utils/readiness";
import {
  formatPrice,
  formatPct,
  formatNum,
  formatMarketCap,
  formatDate,
} from "../lib/formatters";

interface Props {
  row: WatchlistRow;
  /**
   * Phase 9A: callback invoked when the user confirms removal of this company
   * from the active watchlist. Receives the `watchlist_membership_id` and the
   * company ticker (for the confirmation prompt).
   * If omitted, no remove button is rendered.
   */
  onRemove?: (membershipId: string, ticker: string) => void;
  /** Whether a removal is in progress for this row (disables the button). */
  isRemoving?: boolean;
}

function dataQualityLabel(status: string | null): string {
  switch (status) {
    case "healthy":
      return "Healthy";
    case "warning":
      return "Warning";
    case "critical":
      return "Critical";
    case "not_comparable":
      return "Not comparable";
    case "no_diagnostics":
    case null:
      return "No diagnostics";
    default:
      return status.replace(/_/g, " ");
  }
}

function dataQualityBadgeClass(status: string | null): string {
  switch (status) {
    case "healthy":
      return "badge badge--healthy";
    case "warning":
      return "badge badge--warning";
    case "critical":
      return "badge badge--critical";
    case "not_comparable":
      return "badge badge--not-comparable";
    case "no_diagnostics":
    case null:
      return "badge badge--unknown";
    default:
      return "badge badge--unknown";
  }
}

function formatDataQualityCode(code: string): string {
  return code.replace(/_/g, " ");
}

function formatSubStatus(status: string | null): string {
  if (status == null) {
    return "No diagnostics";
  }
  if (status === "ok") {
    return "Healthy";
  }
  return dataQualityLabel(status);
}

/**
 * Single watchlist table row with an expandable detail panel.
 *
 * Compact view shows the key columns from `dashboard_watchlist_latest`.
 * Expanded view shows the signal explanation, red flags, IV range, and
 * key financial ratios stored in the view.
 */
export function CompanyRow({ row, onRemove, isRemoving = false }: Props) {
  const [expanded, setExpanded] = useState(false);

  // can_run_signal === false -> price-only tracking; suppress investment signal display.
  const isTracking = row.can_run_signal === false;

  const ivRange =
    row.iv_p25 != null && row.iv_p75 != null
      ? `${formatPrice(row.iv_p25, row.currency)} - ${formatPrice(row.iv_p75, row.currency)}`
      : "-";

  const ivMid = row.iv_p50 != null ? formatPrice(row.iv_p50, row.currency) : null;

  return (
    <>
      <tr
        className={`company-row ${expanded ? "company-row--expanded" : ""}`}
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setExpanded((v) => !v);
          }
        }}
        title={expanded ? "Click to collapse" : "Click to expand details"}
      >
        <td className="company-row__ticker">
          <span className="ticker-symbol">{row.ticker}</span>
        </td>

        <td className="company-row__name">
          <span className="company-name">{row.name}</span>
          {row.sector && <span className="company-sector">{row.sector}</span>}
          <ResearchQualityBadge
            severity={row.quality_matrix_max_severity}
            primaryCodes={row.quality_matrix_primary_codes}
          />
        </td>

        <td className="company-row__signal">
          {isTracking ? (
            <ReadinessBadge status={row.readiness_status} />
          ) : (
            <SignalBadge signal={row.final_signal} />
          )}
        </td>

        <td className="company-row__price">
          <span>{formatPrice(row.current_price, row.currency)}</span>
          {row.price_date && (
            <span className="date-hint">{formatDate(row.price_date)}</span>
          )}
        </td>

        <td className="company-row__num">
          {isTracking ? (
            <span className="text-muted">-</span>
          ) : row.p_buy_adjusted != null ? (
            <span className={row.p_buy_adjusted >= 0.6 ? "num--positive" : ""}>
              {formatPct(row.p_buy_adjusted)}
            </span>
          ) : (
            <span className="text-muted">-</span>
          )}
        </td>

        <td className="company-row__num">
          {isTracking ? (
            <span className="text-muted">-</span>
          ) : row.p_sell != null ? (
            <span className={row.p_sell >= 0.4 ? "num--negative" : ""}>
              {formatPct(row.p_sell)}
            </span>
          ) : (
            <span className="text-muted">-</span>
          )}
        </td>

        <td className="company-row__num">
          {row.final_quality_score != null ? (
            <span>{formatNum(row.final_quality_score, 0)}</span>
          ) : (
            <span className="text-muted">-</span>
          )}
        </td>

        <td className="company-row__iv">{ivRange}</td>

        <td className="company-row__mos">
          {row.margin_of_safety_conservative != null ? (
            <span
              className={
                row.margin_of_safety_conservative >= 0.2
                  ? "num--positive"
                  : row.margin_of_safety_conservative < 0
                    ? "num--negative"
                    : ""
              }
            >
              {formatPct(row.margin_of_safety_conservative)}
            </span>
          ) : (
            <span className="text-muted">-</span>
          )}
        </td>

        <td className="company-row__freshness">
          <FreshnessTag flag={row.freshness_flag} />
        </td>

        <td
          className="company-row__actions"
          onClick={(e) => e.stopPropagation()}
        >
          {onRemove && (
            <button
              className="btn-action--remove"
              disabled={isRemoving}
              onClick={(e) => {
                e.stopPropagation();
                onRemove(row.watchlist_membership_id, row.ticker);
              }}
              aria-label={`Remove ${row.ticker} from watchlist`}
              title="Remove from watchlist"
            >
              Remove
            </button>
          )}
          <span
            className="company-row__expand"
            aria-hidden="true"
            onClick={(e) => {
              e.stopPropagation();
              setExpanded((v) => !v);
            }}
          >
            {expanded ? "^" : "v"}
          </span>
        </td>
      </tr>

      {expanded && (
        <tr className="company-detail-row">
          <td colSpan={11} className="company-detail-cell">
            <div className="company-detail">
              {isTracking || row.can_run_valuation === false ? (
                <div className="detail-section detail-section--readiness">
                  <h4 className="detail-section__title">Readiness notice</h4>
                  <p className="detail-section__text">
                    {isTracking
                      ? "Price data is available for this company. Valuation and investment signal are not currently available due to provider or data coverage limitations."
                      : "Price data is available for this company. Full valuation is not currently available due to provider or data coverage limitations."}
                  </p>
                  <div className="detail-grid">
                    {row.readiness_status && (
                      <div className="detail-grid__item">
                        <span className="detail-grid__label">Readiness status</span>
                        <span className="detail-grid__value">
                          {readinessLabel(row.readiness_status)}
                        </span>
                      </div>
                    )}
                    {row.provider_mix && (
                      <div className="detail-grid__item">
                        <span className="detail-grid__label">Provider coverage</span>
                        <span className="detail-grid__value">{row.provider_mix}</span>
                      </div>
                    )}
                  </div>
                  {row.readiness_reason_codes && row.readiness_reason_codes.length > 0 && (
                    <ul className="readiness-reason-list">
                      {row.readiness_reason_codes.map((code) => (
                        <li key={code} className="readiness-reason-list__item">
                          {formatReasonCode(code)}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ) : row.explanation ? (
                <div className="detail-section">
                  <h4 className="detail-section__title">Signal explanation</h4>
                  <p className="detail-section__text">{row.explanation}</p>
                </div>
              ) : null}

              <div className="detail-section" data-testid="data-quality-section">
                <div className="detail-section__header">
                  <h4 className="detail-section__title">Data quality</h4>
                  <span
                    className={dataQualityBadgeClass(row.data_quality_status)}
                    data-testid="data-quality-badge"
                  >
                    {dataQualityLabel(row.data_quality_status)}
                  </span>
                </div>
                <p className="detail-section__text">
                  Diagnostic-only validation evidence. These warnings do not change
                  readiness, valuation, or signal labels.
                </p>
                <div className="detail-grid">
                  <div className="detail-grid__item">
                    <span className="detail-grid__label">Overall status</span>
                    <span className="detail-grid__value">
                      {dataQualityLabel(row.data_quality_status)}
                    </span>
                  </div>
                  <div className="detail-grid__item">
                    <span className="detail-grid__label">Warning codes</span>
                    <span className="detail-grid__value">
                      {row.data_quality_warning_codes && row.data_quality_warning_codes.length > 0
                        ? row.data_quality_warning_codes.map(formatDataQualityCode).join(", ")
                        : "None"}
                    </span>
                  </div>
                  <div className="detail-grid__item">
                    <span className="detail-grid__label">Price validation</span>
                    <span className="detail-grid__value">
                      {row.price_validation_status != null
                        ? formatSubStatus(row.price_validation_status)
                        : "-"}
                    </span>
                  </div>
                  <div className="detail-grid__item">
                    <span className="detail-grid__label">Statement completeness</span>
                    <span className="detail-grid__value">
                      {row.statement_completeness_status != null
                        ? `${formatSubStatus(row.statement_completeness_status)}: ${row.statement_completeness_summary ?? "Review diagnostics"}`
                        : "-"}
                    </span>
                  </div>
                  <div className="detail-grid__item">
                    <span className="detail-grid__label">Provider comparison</span>
                    <span className="detail-grid__value">
                      {row.fundamentals_provider_comparison_status != null
                        ? `${formatSubStatus(row.fundamentals_provider_comparison_status)}: ${row.fundamentals_provider_comparison_summary ?? "Review diagnostics"}`
                        : "-"}
                    </span>
                  </div>
                </div>
              </div>

              <div className="detail-section" data-testid="research-quality-section">
                <div className="detail-section__header">
                  <h4 className="detail-section__title">Research quality</h4>
                  <ResearchQualityBadge
                    severity={row.quality_matrix_max_severity}
                    primaryCodes={row.quality_matrix_primary_codes}
                  />
                </div>
                <p className="detail-section__text">
                  Read-only grouping of current data and model diagnostics. It does not
                  change readiness, valuation, or signal labels.
                </p>
                <div className="detail-grid">
                  <div className="detail-grid__item">
                    <span className="detail-grid__label">Quality state</span>
                    <span className="detail-grid__value">
                      {researchQualityLabel(row.quality_matrix_max_severity)}
                    </span>
                  </div>
                  <div className="detail-grid__item">
                    <span className="detail-grid__label">Diagnostic codes</span>
                    <span className="detail-grid__value">
                      {row.quality_matrix_primary_codes && row.quality_matrix_primary_codes.length > 0
                        ? row.quality_matrix_primary_codes.map(formatQualityCode).join(", ")
                        : "None"}
                    </span>
                  </div>
                </div>
              </div>

              <div className="detail-section">
                <h4 className="detail-section__title">Red flags</h4>
                <RedFlagList flags={row.red_flags} />
              </div>

              <div className="detail-section">
                <h4 className="detail-section__title">Intrinsic value range</h4>
                <div className="detail-grid">
                  <div className="detail-grid__item">
                    <span className="detail-grid__label">P25</span>
                    <span className="detail-grid__value">
                      {formatPrice(row.iv_p25, row.currency)}
                    </span>
                  </div>
                  <div className="detail-grid__item">
                    <span className="detail-grid__label">P50 (mid)</span>
                    <span className="detail-grid__value">
                      {ivMid ?? "-"}
                    </span>
                  </div>
                  <div className="detail-grid__item">
                    <span className="detail-grid__label">P75</span>
                    <span className="detail-grid__value">
                      {formatPrice(row.iv_p75, row.currency)}
                    </span>
                  </div>
                  <div className="detail-grid__item">
                    <span className="detail-grid__label">Current price</span>
                    <span className="detail-grid__value">
                      {formatPrice(row.current_price, row.currency)}
                    </span>
                  </div>
                  <div className="detail-grid__item">
                    <span className="detail-grid__label">MoS (conservative)</span>
                    <span className="detail-grid__value">
                      {formatPct(row.margin_of_safety_conservative)}
                    </span>
                  </div>
                  <div className="detail-grid__item">
                    <span className="detail-grid__label">Uncertainty width</span>
                    <span className="detail-grid__value">
                      {formatPct(row.uncertainty_width)}
                    </span>
                  </div>
                </div>
              </div>

              {!isTracking && row.can_run_valuation !== false && (
                <div className="detail-section" data-testid="valuation-diagnostics">
                  <h4 className="detail-section__title">Valuation diagnostics</h4>
                  <div className="detail-grid">
                    <div className="detail-grid__item">
                      <span className="detail-grid__label">MoS basis</span>
                      <span className="detail-grid__value">
                        {row.mos_basis ?? "-"}
                      </span>
                    </div>
                    <div className="detail-grid__item">
                      <span className="detail-grid__label">DCF scenarios</span>
                      <span className="detail-grid__value">
                        {row.scenario_count != null ? `${row.scenario_count}/3` : "-"}
                      </span>
                    </div>
                    <div className="detail-grid__item">
                      <span className="detail-grid__label">Valuation uncertainty</span>
                      <span className="detail-grid__value">
                        {row.uncertainty_category != null
                          ? row.uncertainty_category.charAt(0).toUpperCase() +
                            row.uncertainty_category.slice(1)
                          : "-"}
                      </span>
                    </div>
                  </div>
                  {row.distribution_collapsed === true && (
                    <p
                      className="detail-section__warning"
                      data-testid="distribution-collapsed-warning"
                    >
                      Valuation distribution collapsed - limited scenario/method diversity.
                    </p>
                  )}
                </div>
              )}

              <div className="detail-section">
                <h4 className="detail-section__title">Key ratios</h4>
                <div className="detail-grid">
                  <div className="detail-grid__item">
                    <span className="detail-grid__label">ROIC</span>
                    <span className="detail-grid__value">
                      {formatPct(row.roic)}
                    </span>
                  </div>
                  <div className="detail-grid__item">
                    <span className="detail-grid__label">FCF Yield</span>
                    <span className="detail-grid__value">
                      {formatPct(row.fcf_yield)}
                    </span>
                  </div>
                  <div className="detail-grid__item">
                    <span className="detail-grid__label">Net Debt / EBITDA</span>
                    <span className="detail-grid__value">
                      {formatNum(row.net_debt_to_ebitda)}
                    </span>
                  </div>
                  <div className="detail-grid__item">
                    <span className="detail-grid__label">News Sentiment (7d)</span>
                    <span className="detail-grid__value">
                      {formatNum(row.news_sentiment_7d)}
                    </span>
                  </div>
                  <div className="detail-grid__item">
                    <span className="detail-grid__label">Market Cap</span>
                    <span className="detail-grid__value">
                      {formatMarketCap(row.market_cap)}
                    </span>
                  </div>
                  <div className="detail-grid__item">
                    <span className="detail-grid__label">p_buy (raw)</span>
                    <span className="detail-grid__value">
                      {isTracking ? (
                        <span className="text-muted">-</span>
                      ) : (
                        formatPct(row.p_buy)
                      )}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
