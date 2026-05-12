import React from "react";
import type { SignalFilter, SortKey } from "../types";

interface Props {
  filter: SignalFilter;
  onFilterChange: (f: SignalFilter) => void;
  sortKey: SortKey;
  onSortKeyChange: (k: SortKey) => void;
  sortAsc: boolean;
  onSortAscChange: (asc: boolean) => void;
  tickerSearch: string;
  onTickerSearchChange: (q: string) => void;
  totalCount: number;
  filteredCount: number;
}

const SIGNAL_FILTERS: SignalFilter[] = [
  "ALL",
  "BUY",
  "STRONG_BUY",
  "HOLD",
  "INSUFFICIENT_DATA",
  "SELL",
  "STRONG_SELL",
];

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "ticker", label: "Ticker (A–Z)" },
  { value: "p_buy_adjusted", label: "p_buy_adjusted" },
  { value: "margin_of_safety_conservative", label: "Margin of Safety" },
  { value: "final_quality_score", label: "Quality Score" },
  { value: "final_signal", label: "Signal" },
];

/**
 * Watchlist filter and sort controls.
 */
export function FilterBar({
  filter,
  onFilterChange,
  sortKey,
  onSortKeyChange,
  sortAsc,
  onSortAscChange,
  tickerSearch,
  onTickerSearchChange,
  totalCount,
  filteredCount,
}: Props) {
  return (
    <div className="filter-bar" role="search" aria-label="Watchlist filters">
      <div className="filter-bar__group">
        <label className="filter-bar__label" htmlFor="ticker-search">
          Search
        </label>
        <input
          id="ticker-search"
          type="text"
          className="filter-bar__input"
          placeholder="Ticker or name…"
          value={tickerSearch}
          onChange={(e) => onTickerSearchChange(e.target.value)}
          aria-label="Search by ticker or company name"
        />
      </div>

      <div className="filter-bar__group">
        <label className="filter-bar__label">Signal</label>
        <div className="filter-bar__pills" role="radiogroup" aria-label="Filter by signal">
          {SIGNAL_FILTERS.map((f) => (
            <button
              key={f}
              className={`filter-pill ${filter === f ? "filter-pill--active" : ""}`}
              onClick={() => onFilterChange(f)}
              role="radio"
              aria-checked={filter === f}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-bar__group">
        <label className="filter-bar__label" htmlFor="sort-select">
          Sort
        </label>
        <select
          id="sort-select"
          className="filter-bar__select"
          value={sortKey}
          onChange={(e) => onSortKeyChange(e.target.value as SortKey)}
          aria-label="Sort by"
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <button
          className="filter-bar__sort-dir"
          onClick={() => onSortAscChange(!sortAsc)}
          title={sortAsc ? "Ascending — click to switch to descending" : "Descending — click to switch to ascending"}
          aria-label={sortAsc ? "Sort ascending" : "Sort descending"}
        >
          {sortAsc ? "↑" : "↓"}
        </button>
      </div>

      <div className="filter-bar__count" aria-live="polite">
        {filteredCount === totalCount
          ? `${totalCount} companies`
          : `${filteredCount} of ${totalCount} companies`}
      </div>
    </div>
  );
}
