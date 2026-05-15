import React, { useState } from "react";
import type { WatchlistRow } from "../types";
import { SignalBadge } from "./SignalBadge";
import { ReadinessBadge } from "./ReadinessBadge";
import { FreshnessTag } from "./FreshnessTag";
import { RedFlagList } from "./RedFlagList";
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
   * from the active watchlist.  Receives the `watchlist_membership_id` and the
   * company ticker (for the confirmation prompt).
   * If omitted, no remove button is rendered.
   */
  onRemove?: (membershipId: string, ticker: string) => void;
  /** Whether a removal is in progress for this row (disables the button). */
  isRemoving?: boolean;
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

  // can_run_signal === false → price-only tracking; suppress investment signal display.
  const isTracking = row.can_run_signal === false;

  const ivRange =
    row.iv_p25 != null && row.iv_p75 != null
      ? `${formatPrice(row.iv_p25, row.currency)} – ${formatPrice(row.iv_p75, row.currency)}`
      : "—";

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
        {/* Ticker */}
        <td className="company-row__ticker">
          <span className="ticker-symbol">{row.ticker}</span>
        </td>

        {/* Company name */}
        <td className="company-row__name">
          <span className="company-name">{row.name}</span>
          {row.sector && <span className="company-sector">{row.sector}</span>}
        </td>

        {/* Signal / Readiness */}
        <td className="company-row__signal">
          {isTracking ? (
            <ReadinessBadge status={row.readiness_status} />
          ) : (
            <SignalBadge signal={row.final_signal} />
          )}
        </td>

        {/* Price */}
        <td className="company-row__price">
          <span>{formatPrice(row.current_price, row.currency)}</span>
          {row.price_date && (
            <span className="date-hint">{formatDate(row.price_date)}</span>
          )}
        </td>

        {/* p_buy_adjusted — hidden for tracking-only rows */}
        <td className="company-row__num">
          {isTracking ? (
            <span className="text-muted">—</span>
          ) : row.p_buy_adjusted != null ? (
            <span className={row.p_buy_adjusted >= 0.6 ? "num--positive" : ""}>
              {formatPct(row.p_buy_adjusted)}
            </span>
          ) : (
            <span className="text-muted">—</span>
          )}
        </td>

        {/* p_sell — hidden for tracking-only rows */}
        <td className="company-row__num">
          {isTracking ? (
            <span className="text-muted">—</span>
          ) : row.p_sell != null ? (
            <span className={row.p_sell >= 0.4 ? "num--negative" : ""}>
              {formatPct(row.p_sell)}
            </span>
          ) : (
            <span className="text-muted">—</span>
          )}
        </td>

        {/* Quality score */}
        <td className="company-row__num">
          {row.final_quality_score != null ? (
            <span>{formatNum(row.final_quality_score, 0)}</span>
          ) : (
            <span className="text-muted">—</span>
          )}
        </td>

        {/* IV Range */}
        <td className="company-row__iv">{ivRange}</td>

        {/* Margin of safety */}
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
            <span className="text-muted">—</span>
          )}
        </td>

        {/* Freshness */}
        <td className="company-row__freshness">
          <FreshnessTag flag={row.freshness_flag} />
        </td>

        {/* Actions: remove button + expand chevron */}
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
              ✕
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
            {expanded ? "▲" : "▼"}
          </span>
        </td>
      </tr>

      {expanded && (
        <tr className="company-detail-row">
          <td colSpan={11} className="company-detail-cell">
            <div className="company-detail">
              {/* Readiness notice (tracking/partial) or signal explanation (analysis-ready) */}
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

              {/* Red flags */}
              <div className="detail-section">
                <h4 className="detail-section__title">Red flags</h4>
                <RedFlagList flags={row.red_flags} />
              </div>

              {/* Valuation range */}
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
                      {ivMid ?? "—"}
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

              {/* Key ratios */}
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
                        <span className="text-muted">—</span>
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
