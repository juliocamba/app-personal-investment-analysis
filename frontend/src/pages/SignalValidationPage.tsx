import React, { useEffect, useMemo, useState } from "react";
import {
  fetchSignalBacktestByDataQuality,
  fetchSignalBacktestByReadiness,
  fetchSignalBacktestBySector,
  fetchSignalBacktestCoverageRows,
  fetchSignalBacktestSummaryByBucket,
  fetchSignalBacktestSummaryByHorizon,
  fetchSignalBacktestStability,
} from "../lib/api";
import { formatPct } from "../lib/formatters";
import type {
  SignalBacktestBucketSummaryRow,
  SignalBacktestCoverageRow,
  SignalBacktestHorizonSummaryRow,
  SignalBacktestSegmentSummaryRow,
  SignalBacktestStabilityRow,
} from "../types";

function formatPercentOrDash(value: number | null | undefined): string {
  if (value == null) return "-";
  return formatPct(value, 1);
}

function formatSignal(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatStatusLabel(value: string | undefined): string {
  if (!value) return "Unknown";
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatHorizonLabel(horizonDays: number): string {
  return `${horizonDays}d`;
}

interface SegmentTableProps {
  title: string;
  ariaLabel: string;
  rows: SignalBacktestSegmentSummaryRow[];
  labelKey: "readiness_status_at_signal" | "data_quality_status_at_signal" | "sector_at_signal";
}

function SegmentTable({ title, ariaLabel, rows, labelKey }: SegmentTableProps) {
  return (
    <section className="portfolio-panel" aria-label={ariaLabel}>
      <h2 className="portfolio-panel__title">{title}</h2>
      <div className="table-wrapper">
        <table className="positions-table" aria-label={ariaLabel}>
          <thead>
            <tr>
              <th scope="col">Segment</th>
              <th scope="col">Signal bucket</th>
              <th scope="col">Horizon</th>
              <th scope="col">Observations</th>
              <th scope="col">Average return</th>
              <th scope="col">Median return</th>
              <th scope="col">Hit rate</th>
              <th scope="col">Coverage</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row[labelKey] ?? "unknown"}-${row.final_signal}-${row.horizon_days}`}>
                <td>{formatStatusLabel(row[labelKey])}</td>
                <td>{formatSignal(row.final_signal)}</td>
                <td>{formatHorizonLabel(row.horizon_days)}</td>
                <td>{row.observation_count}</td>
                <td>{formatPercentOrDash(row.average_return)}</td>
                <td>{formatPercentOrDash(row.median_return)}</td>
                <td>{formatPercentOrDash(row.hit_rate)}</td>
                <td>{formatPercentOrDash(row.coverage_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function SignalValidationPage() {
  const [bucketRows, setBucketRows] = useState<SignalBacktestBucketSummaryRow[]>([]);
  const [horizonRows, setHorizonRows] = useState<SignalBacktestHorizonSummaryRow[]>([]);
  const [readinessRows, setReadinessRows] = useState<SignalBacktestSegmentSummaryRow[]>([]);
  const [dataQualityRows, setDataQualityRows] = useState<SignalBacktestSegmentSummaryRow[]>([]);
  const [sectorRows, setSectorRows] = useState<SignalBacktestSegmentSummaryRow[]>([]);
  const [stabilityRows, setStabilityRows] = useState<SignalBacktestStabilityRow[]>([]);
  const [coverageRows, setCoverageRows] = useState<SignalBacktestCoverageRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetchSignalBacktestSummaryByBucket(),
      fetchSignalBacktestSummaryByHorizon(),
      fetchSignalBacktestByReadiness(),
      fetchSignalBacktestByDataQuality(),
      fetchSignalBacktestBySector(),
      fetchSignalBacktestStability(),
      fetchSignalBacktestCoverageRows(),
    ])
      .then(([
        bucketSummary,
        horizonSummary,
        readinessSummary,
        dataQualitySummary,
        sectorSummary,
        stabilitySummary,
        coverageSummaryRows,
      ]) => {
        setBucketRows(bucketSummary);
        setHorizonRows(horizonSummary);
        setReadinessRows(readinessSummary);
        setDataQualityRows(dataQualitySummary);
        setSectorRows(sectorSummary);
        setStabilityRows(stabilitySummary);
        setCoverageRows(coverageSummaryRows);
        setLoading(false);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
  }, []);

  const coverageSummary = useMemo(
    () =>
      horizonRows.map((row) => ({
        label: formatHorizonLabel(row.horizon_days),
        coverage: formatPercentOrDash(row.coverage_pct),
        observations: row.observation_count,
      })),
    [horizonRows],
  );

  const coverageLimitations = useMemo(() => {
    const total = coverageRows.length;
    return {
      unknownReadinessCount: coverageRows.filter((row) => !row.readiness_status_at_signal).length,
      unknownDataQualityCount: coverageRows.filter((row) => !row.data_quality_status_at_signal).length,
      unknownSectorCount: coverageRows.filter((row) => !row.sector_at_signal).length,
      missing30dCount: coverageRows.filter((row) => !row.has_price_30d).length,
      missing90dCount: coverageRows.filter((row) => !row.has_price_90d).length,
      missing180dCount: coverageRows.filter((row) => !row.has_price_180d).length,
      missing365dCount: coverageRows.filter((row) => !row.has_price_365d).length,
      totalObservations: total,
    };
  }, [coverageRows]);

  if (loading) {
    return (
      <div className="page-state" aria-live="polite" aria-busy="true">
        <div className="spinner" aria-label="Loading signal validation..." />
        <p>Loading signal validation...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-state page-state--error" role="alert">
        <p className="page-state__title">Failed to load signal validation</p>
        <p className="page-state__detail">{error}</p>
      </div>
    );
  }

  if (bucketRows.length === 0 || horizonRows.length === 0) {
    return (
      <div className="page">
        <div className="page__header">
          <h1 className="page__title">Signal Validation</h1>
        </div>
        <div className="page-state" aria-live="polite">
          <p className="page-state__title">No historical validation observations yet</p>
          <p className="page-state__detail">
            Run the separate signal validation refresh job first to populate the research dataset.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page__header">
        <h1 className="page__title">Signal Validation</h1>
        <span className="page__subtitle">Historical validation only from persisted signal and price history</span>
      </div>

      <section className="portfolio-banner" role="status" aria-live="polite">
        <p className="portfolio-banner__title">Research caveats</p>
        <p className="portfolio-banner__text">
          Price return only. Historical validation only. Coverage gaps remain explicit, no future guarantee is implied, and this is not a strategy simulation.
        </p>
        <p className="portfolio-banner__text">
          Readiness at signal may be sparse when that historical field was not captured at the time. Sector at signal reflects stored historical classification context and may not match later reclassifications. Missing forward prices remain not available rather than estimated.
        </p>
      </section>

      <section className="portfolio-summary" aria-label="Coverage summary">
        {coverageSummary.map((item) => (
          <article className="portfolio-card" key={item.label}>
            <span className="portfolio-card__label">{item.label} coverage</span>
            <span className="portfolio-card__value">{item.coverage}</span>
            <span className="portfolio-panel__text">{item.observations} observations</span>
          </article>
        ))}
      </section>

      <section className="portfolio-summary" aria-label="Coverage limitations summary">
        <article className="portfolio-card">
          <span className="portfolio-card__label">Unknown readiness at signal</span>
          <span className="portfolio-card__value">{coverageLimitations.unknownReadinessCount}</span>
          <span className="portfolio-panel__text">
            {coverageLimitations.totalObservations} total observations
          </span>
        </article>
        <article className="portfolio-card">
          <span className="portfolio-card__label">Unknown data quality at signal</span>
          <span className="portfolio-card__value">{coverageLimitations.unknownDataQualityCount}</span>
          <span className="portfolio-panel__text">
            Historical status was not available
          </span>
        </article>
        <article className="portfolio-card">
          <span className="portfolio-card__label">Unknown sector at signal</span>
          <span className="portfolio-card__value">{coverageLimitations.unknownSectorCount}</span>
          <span className="portfolio-panel__text">
            Stored classification context was not available
          </span>
        </article>
      </section>

      <section className="portfolio-summary" aria-label="Forward coverage gaps">
        <article className="portfolio-card">
          <span className="portfolio-card__label">30d coverage gap</span>
          <span className="portfolio-card__value">{coverageLimitations.missing30dCount}</span>
          <span className="portfolio-panel__text">Forward price not available</span>
        </article>
        <article className="portfolio-card">
          <span className="portfolio-card__label">90d coverage gap</span>
          <span className="portfolio-card__value">{coverageLimitations.missing90dCount}</span>
          <span className="portfolio-panel__text">Forward price not available</span>
        </article>
        <article className="portfolio-card">
          <span className="portfolio-card__label">180d coverage gap</span>
          <span className="portfolio-card__value">{coverageLimitations.missing180dCount}</span>
          <span className="portfolio-panel__text">Forward price not available</span>
        </article>
        <article className="portfolio-card">
          <span className="portfolio-card__label">365d coverage gap</span>
          <span className="portfolio-card__value">{coverageLimitations.missing365dCount}</span>
          <span className="portfolio-panel__text">Forward price not available</span>
        </article>
      </section>

      <section className="portfolio-panel" aria-label="Horizon comparison">
        <h2 className="portfolio-panel__title">Horizon comparison</h2>
        <div className="table-wrapper">
          <table className="positions-table" aria-label="Signal validation horizon comparison">
            <thead>
              <tr>
                <th scope="col">Horizon</th>
                <th scope="col">Observations</th>
                <th scope="col">Average return</th>
                <th scope="col">Median return</th>
                <th scope="col">Hit rate</th>
                <th scope="col">Coverage</th>
              </tr>
            </thead>
            <tbody>
              {horizonRows.map((row) => (
                <tr key={row.horizon_days}>
                  <td>{formatHorizonLabel(row.horizon_days)}</td>
                  <td>{row.observation_count}</td>
                  <td>{formatPercentOrDash(row.average_return)}</td>
                  <td>{formatPercentOrDash(row.median_return)}</td>
                  <td>{formatPercentOrDash(row.hit_rate)}</td>
                  <td>{formatPercentOrDash(row.coverage_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="portfolio-panel" aria-label="Returns by signal bucket">
        <h2 className="portfolio-panel__title">Returns by signal bucket</h2>
        <div className="table-wrapper">
          <table className="positions-table" aria-label="Signal validation returns by signal bucket">
            <thead>
              <tr>
                <th scope="col">Signal bucket</th>
                <th scope="col">Horizon</th>
                <th scope="col">Observations</th>
                <th scope="col">Average return</th>
                <th scope="col">Median return</th>
                <th scope="col">Hit rate</th>
                <th scope="col">Coverage</th>
              </tr>
            </thead>
            <tbody>
              {bucketRows.map((row) => (
                <tr key={`${row.final_signal}-${row.horizon_days}`}>
                  <td>{formatSignal(row.final_signal)}</td>
                  <td>{formatHorizonLabel(row.horizon_days)}</td>
                  <td>{row.observation_count}</td>
                  <td>{formatPercentOrDash(row.average_return)}</td>
                  <td>{formatPercentOrDash(row.median_return)}</td>
                  <td>{formatPercentOrDash(row.hit_rate)}</td>
                  <td>{formatPercentOrDash(row.coverage_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <SegmentTable
        title="Readiness breakdown"
        ariaLabel="Readiness breakdown"
        rows={readinessRows}
        labelKey="readiness_status_at_signal"
      />

      <SegmentTable
        title="Data-quality breakdown"
        ariaLabel="Data-quality breakdown"
        rows={dataQualityRows}
        labelKey="data_quality_status_at_signal"
      />

      <SegmentTable
        title="Sector breakdown"
        ariaLabel="Sector breakdown"
        rows={sectorRows}
        labelKey="sector_at_signal"
      />

      <section className="portfolio-panel" aria-label="Signal stability">
        <h2 className="portfolio-panel__title">Signal stability</h2>
        <div className="table-wrapper">
          <table className="positions-table" aria-label="Signal stability">
            <thead>
              <tr>
                <th scope="col">Signal bucket</th>
                <th scope="col">Observations</th>
                <th scope="col">Transitions</th>
                <th scope="col">Flips</th>
                <th scope="col">Stable transitions</th>
                <th scope="col">Flip rate</th>
                <th scope="col">Stability %</th>
                <th scope="col">Avg days to next signal</th>
              </tr>
            </thead>
            <tbody>
              {stabilityRows.map((row) => (
                <tr key={row.signal_bucket}>
                  <td>{formatSignal(row.signal_bucket)}</td>
                  <td>{row.observation_count}</td>
                  <td>{row.transition_count}</td>
                  <td>{row.flip_count}</td>
                  <td>{row.stable_transition_count}</td>
                  <td>{formatPercentOrDash(row.flip_rate)}</td>
                  <td>{formatPercentOrDash(row.stability_pct)}</td>
                  <td>{row.average_days_to_next_signal == null ? "-" : row.average_days_to_next_signal.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <p className="page__footer-note">
        These summaries are descriptive validation only. They validate persisted signal buckets against later stored prices, they do not simulate a tradable strategy, they do not imply a future edge, and they do not change live model behavior.
      </p>
    </div>
  );
}
