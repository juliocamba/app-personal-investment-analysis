import React, { useEffect, useMemo, useState } from "react";
import {
  closePosition,
  createPosition,
  fetchCompaniesForPositions,
  fetchPositionEntryProfiles,
  fetchPositions,
  savePositionEntryProfile,
  updatePosition,
} from "../lib/api";
import { formatDate, formatPct, formatPrice, formatNum } from "../lib/formatters";
import type {
  CompanyOption,
  PositionDashboardRow,
  PositionEntryProfileInput,
  PositionEntryProfileRow,
  PositionInput,
} from "../types";

interface PositionFormState {
  company_id: string;
  entry_date: string;
  quantity: string;
  average_entry_price: string;
  currency: string;
  fees: string;
  notes: string;
  status: "active" | "closed";
  closed_at: string;
  thesis_summary: string;
  why_bought: string;
  key_risks: string;
  target_price: string;
  target_price_currency: string;
  expected_holding_period: string;
  confidence_level: "" | "low" | "medium" | "high";
  catalysts: string;
  invalidation_criteria: string;
}

const EMPTY_FORM: PositionFormState = {
  company_id: "",
  entry_date: "",
  quantity: "",
  average_entry_price: "",
  currency: "USD",
  fees: "",
  notes: "",
  status: "active",
  closed_at: "",
  thesis_summary: "",
  why_bought: "",
  key_risks: "",
  target_price: "",
  target_price_currency: "USD",
  expected_holding_period: "",
  confidence_level: "",
  catalysts: "",
  invalidation_criteria: "",
};

function statusLabel(status: PositionDashboardRow["status"]): string {
  return status === "active" ? "Active" : "Closed";
}

function formatDisplayPrice(value: number | null, currency: string | null): string {
  if (value == null || !currency) return "-";
  return formatPrice(value, currency);
}

function formatDisplayPercent(value: number | null): string {
  if (value == null) return "-";
  return formatPct(value, 1);
}

function formatDisplayText(value: string | null | undefined): string {
  if (!value) return "-";
  return value;
}

function formatStatusText(value: string | null | undefined): string {
  if (!value) return "-";
  if (value === value.toUpperCase()) return value;
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatValuationRange(
  low: number | null,
  mid: number | null,
  high: number | null,
  currency: string | null,
): string {
  if (low == null || mid == null || high == null || !currency) return "-";
  return `${formatPrice(low, currency)} / ${formatPrice(mid, currency)} / ${formatPrice(high, currency)}`;
}

function formatPriceWithDate(
  value: number | null,
  currency: string | null,
  date: string | null | undefined,
): string {
  if (value == null || !currency) return "-";
  const dateText = formatDate(date ?? null);
  return dateText === "-" ? formatPrice(value, currency) : `${formatPrice(value, currency)} (${dateText})`;
}

function displayClass(value: number | null): string | undefined {
  if (value == null || value === 0) return undefined;
  return value > 0 ? "num--positive" : "num--negative";
}

function buildPositionPayload(form: PositionFormState): PositionInput {
  return {
    company_id: form.company_id,
    entry_date: form.entry_date,
    quantity: Number(form.quantity),
    average_entry_price: Number(form.average_entry_price),
    currency: form.currency,
    fees: form.fees.trim() ? Number(form.fees) : null,
    notes: form.notes.trim() || null,
    status: form.status,
    closed_at: form.status === "closed" && form.closed_at ? form.closed_at : null,
  };
}

function buildEntryProfilePayload(form: PositionFormState): PositionEntryProfileInput {
  return {
    thesis_summary: form.thesis_summary,
    why_bought: form.why_bought,
    key_risks: form.key_risks,
    target_price: form.target_price.trim() ? Number(form.target_price) : null,
    target_price_currency: form.target_price_currency,
    expected_holding_period: form.expected_holding_period,
    confidence_level: form.confidence_level || null,
    catalysts: form.catalysts,
    invalidation_criteria: form.invalidation_criteria,
  };
}

function hasAnyThesisInput(payload: PositionEntryProfileInput): boolean {
  return Boolean(
    payload.thesis_summary
      || payload.why_bought
      || payload.key_risks
      || payload.target_price != null
      || payload.expected_holding_period
      || payload.confidence_level
      || payload.catalysts
      || payload.invalidation_criteria,
  );
}

export function PositionsPage() {
  const [positions, setPositions] = useState<PositionDashboardRow[]>([]);
  const [profiles, setProfiles] = useState<PositionEntryProfileRow[]>([]);
  const [companies, setCompanies] = useState<CompanyOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [closingId, setClosingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showThesisFields, setShowThesisFields] = useState(false);
  const [form, setForm] = useState<PositionFormState>(EMPTY_FORM);

  async function loadPageState(): Promise<void> {
    const [positionRows, companyRows, profileRows] = await Promise.all([
      fetchPositions(),
      fetchCompaniesForPositions(),
      fetchPositionEntryProfiles(),
    ]);
    setPositions(positionRows);
    setCompanies(companyRows);
    setProfiles(profileRows);
    if (companyRows.length > 0) {
      setForm((prev) => ({
        ...prev,
        company_id: prev.company_id || companyRows[0].id,
        currency: prev.currency || companyRows[0].currency || "USD",
        target_price_currency: prev.target_price_currency || prev.currency || companyRows[0].currency || "USD",
      }));
    }
  }

  async function refreshPositionData(): Promise<void> {
    const [positionRows, profileRows] = await Promise.all([
      fetchPositions(),
      fetchPositionEntryProfiles(),
    ]);
    setPositions(positionRows);
    setProfiles(profileRows);
  }

  useEffect(() => {
    loadPageState()
      .then(() => {
        setLoading(false);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
  }, []);

  const companyMap = useMemo(
    () => new Map(companies.map((company) => [company.id, company])),
    [companies],
  );

  const profileMap = useMemo(
    () => new Map(profiles.map((profile) => [profile.position_id, profile])),
    [profiles],
  );

  function resetForm(nextCompanies = companies): void {
    setEditingId(null);
    setSaveError(null);
    setShowThesisFields(false);
    setForm({
      ...EMPTY_FORM,
      company_id: nextCompanies[0]?.id ?? "",
      currency: nextCompanies[0]?.currency ?? "USD",
      target_price_currency: nextCompanies[0]?.currency ?? "USD",
    });
  }

  function handleCompanyChange(companyId: string): void {
    const selected = companyMap.get(companyId);
    setForm((prev) => ({
      ...prev,
      company_id: companyId,
      currency: selected?.currency ?? prev.currency,
      target_price_currency: prev.target_price_currency || selected?.currency || prev.currency,
    }));
  }

  function handleEdit(position: PositionDashboardRow): void {
    const profile = profileMap.get(position.id);
    setEditingId(position.id);
    setSaveError(null);
    setShowThesisFields(Boolean(
      profile?.thesis_summary
        || profile?.why_bought
        || profile?.key_risks
        || profile?.target_price != null
        || profile?.expected_holding_period
        || profile?.confidence_level
        || profile?.catalysts
        || profile?.invalidation_criteria,
    ));
    setForm({
      company_id: position.company_id,
      entry_date: position.entry_date,
      quantity: String(position.quantity),
      average_entry_price: String(position.average_entry_price),
      currency: position.currency,
      fees: position.fees != null ? String(position.fees) : "",
      notes: position.notes ?? "",
      status: position.status,
      closed_at: position.closed_at ? position.closed_at.slice(0, 10) : "",
      thesis_summary: profile?.thesis_summary ?? "",
      why_bought: profile?.why_bought ?? "",
      key_risks: profile?.key_risks ?? "",
      target_price: profile?.target_price != null ? String(profile.target_price) : "",
      target_price_currency: profile?.target_price_currency ?? position.currency,
      expected_holding_period: profile?.expected_holding_period ?? "",
      confidence_level: profile?.confidence_level ?? "",
      catalysts: profile?.catalysts ?? "",
      invalidation_criteria: profile?.invalidation_criteria ?? "",
    });
  }

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setIsSaving(true);
    setSaveError(null);
    try {
      const positionPayload = buildPositionPayload(form);
      const thesisPayload = buildEntryProfilePayload(form);
      let positionId = editingId;

      if (editingId) {
        const updated = await updatePosition(editingId, positionPayload);
        positionId = updated.id;
      } else {
        const created = await createPosition(positionPayload);
        positionId = created.id;
      }

      if (positionId && (showThesisFields || hasAnyThesisInput(thesisPayload))) {
        await savePositionEntryProfile(positionId, thesisPayload);
      }

      await refreshPositionData();
      resetForm();
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleClose(positionId: string): Promise<void> {
    setClosingId(positionId);
    setSaveError(null);
    try {
      await closePosition(positionId);
      await refreshPositionData();
      if (editingId === positionId) {
        resetForm();
      }
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : String(err));
    } finally {
      setClosingId(null);
    }
  }

  if (loading) {
    return (
      <div className="page-state" aria-live="polite" aria-busy="true">
        <div className="spinner" aria-label="Loading positions..." />
        <p>Loading positions...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-state page-state--error" role="alert">
        <p className="page-state__title">Failed to load positions</p>
        <p className="page-state__detail">{error}</p>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page__header">
        <h1 className="page__title">Positions</h1>
        <span className="page__subtitle">{positions.length} tracked positions</span>
      </div>

      <section className="positions-panel" aria-labelledby="positions-form-title">
        <div className="positions-panel__header">
          <h2 id="positions-form-title" className="positions-panel__title">
            {editingId ? "Edit position" : "Add position"}
          </h2>
          {editingId && (
            <button
              type="button"
              className="positions-btn positions-btn--ghost"
              onClick={() => resetForm()}
            >
              Cancel edit
            </button>
          )}
        </div>

        <form className="positions-form" onSubmit={handleSubmit}>
          <label className="positions-form__field">
            <span>Company</span>
            <select
              value={form.company_id}
              onChange={(e) => handleCompanyChange(e.target.value)}
              required
            >
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.ticker} - {company.name}
                </option>
              ))}
            </select>
          </label>

          <label className="positions-form__field">
            <span>Entry date</span>
            <input
              type="date"
              value={form.entry_date}
              onChange={(e) => setForm((prev) => ({ ...prev, entry_date: e.target.value }))}
              required
            />
          </label>

          <label className="positions-form__field">
            <span>Quantity</span>
            <input
              type="number"
              min="0.000001"
              step="0.000001"
              value={form.quantity}
              onChange={(e) => setForm((prev) => ({ ...prev, quantity: e.target.value }))}
              required
            />
          </label>

          <label className="positions-form__field">
            <span>Average entry price</span>
            <input
              type="number"
              min="0.000001"
              step="0.000001"
              value={form.average_entry_price}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, average_entry_price: e.target.value }))
              }
              required
            />
          </label>

          <label className="positions-form__field">
            <span>Currency</span>
            <input
              type="text"
              value={form.currency}
              maxLength={10}
              onChange={(e) => setForm((prev) => ({ ...prev, currency: e.target.value }))}
              required
            />
          </label>

          <label className="positions-form__field">
            <span>Fees</span>
            <input
              type="number"
              min="0"
              step="0.01"
              value={form.fees}
              onChange={(e) => setForm((prev) => ({ ...prev, fees: e.target.value }))}
            />
          </label>

          <label className="positions-form__field">
            <span>Status</span>
            <select
              value={form.status}
              onChange={(e) =>
                setForm((prev) => ({
                  ...prev,
                  status: e.target.value as "active" | "closed",
                  closed_at: e.target.value === "active" ? "" : prev.closed_at,
                }))
              }
            >
              <option value="active">Active</option>
              <option value="closed">Closed</option>
            </select>
          </label>

          {form.status === "closed" && (
            <label className="positions-form__field">
              <span>Closed date</span>
              <input
                type="date"
                value={form.closed_at}
                onChange={(e) => setForm((prev) => ({ ...prev, closed_at: e.target.value }))}
              />
            </label>
          )}

          <label className="positions-form__field positions-form__field--wide">
            <span>Notes</span>
            <textarea
              value={form.notes}
              rows={3}
              onChange={(e) => setForm((prev) => ({ ...prev, notes: e.target.value }))}
            />
          </label>

          <div className="positions-form__actions positions-form__actions--split">
            <button
              type="button"
              className="positions-btn positions-btn--ghost"
              onClick={() => setShowThesisFields((prev) => !prev)}
            >
              {showThesisFields ? "Hide entry thesis" : "Add entry thesis"}
            </button>
            <button
              type="submit"
              className="positions-btn"
              disabled={isSaving || companies.length === 0}
            >
              {isSaving ? "Saving..." : editingId ? "Save changes" : "Add position"}
            </button>
          </div>

          {showThesisFields && (
            <div className="positions-thesis">
              <h3 className="positions-thesis__title">Entry thesis</h3>

              <label className="positions-form__field positions-form__field--wide">
                <span>Thesis summary</span>
                <textarea
                  value={form.thesis_summary}
                  rows={2}
                  onChange={(e) => setForm((prev) => ({ ...prev, thesis_summary: e.target.value }))}
                />
              </label>

              <label className="positions-form__field positions-form__field--wide">
                <span>Why I bought</span>
                <textarea
                  value={form.why_bought}
                  rows={3}
                  onChange={(e) => setForm((prev) => ({ ...prev, why_bought: e.target.value }))}
                />
              </label>

              <label className="positions-form__field positions-form__field--wide">
                <span>Key risks</span>
                <textarea
                  value={form.key_risks}
                  rows={3}
                  onChange={(e) => setForm((prev) => ({ ...prev, key_risks: e.target.value }))}
                />
              </label>

              <label className="positions-form__field">
                <span>Target price</span>
                <input
                  type="number"
                  min="0.000001"
                  step="0.000001"
                  value={form.target_price}
                  onChange={(e) => setForm((prev) => ({ ...prev, target_price: e.target.value }))}
                />
              </label>

              <label className="positions-form__field">
                <span>Target price currency</span>
                <input
                  type="text"
                  maxLength={10}
                  value={form.target_price_currency}
                  onChange={(e) =>
                    setForm((prev) => ({ ...prev, target_price_currency: e.target.value }))
                  }
                />
              </label>

              <label className="positions-form__field">
                <span>Expected holding period</span>
                <input
                  type="text"
                  value={form.expected_holding_period}
                  onChange={(e) =>
                    setForm((prev) => ({ ...prev, expected_holding_period: e.target.value }))
                  }
                />
              </label>

              <label className="positions-form__field">
                <span>Confidence level</span>
                <select
                  value={form.confidence_level}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      confidence_level: e.target.value as "" | "low" | "medium" | "high",
                    }))
                  }
                >
                  <option value="">-</option>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </label>

              <label className="positions-form__field positions-form__field--wide">
                <span>Catalysts</span>
                <textarea
                  value={form.catalysts}
                  rows={2}
                  onChange={(e) => setForm((prev) => ({ ...prev, catalysts: e.target.value }))}
                />
              </label>

              <label className="positions-form__field positions-form__field--wide">
                <span>Invalidation criteria</span>
                <textarea
                  value={form.invalidation_criteria}
                  rows={2}
                  onChange={(e) =>
                    setForm((prev) => ({ ...prev, invalidation_criteria: e.target.value }))
                  }
                />
              </label>
            </div>
          )}
        </form>

        {saveError && (
          <p className="positions-panel__error" role="alert">
            {saveError}
          </p>
        )}
      </section>

      {positions.length === 0 ? (
        <div className="page-state" aria-live="polite">
          <p className="page-state__title">No positions yet</p>
          <p className="page-state__detail">
            Add positions manually to track what you currently own. This does not
            change signals, readiness, or alerts.
          </p>
        </div>
      ) : (
        <>
          <div className="table-wrapper">
            <table className="positions-table" aria-label="Manual positions">
              <thead>
                <tr>
                  <th scope="col">Ticker</th>
                  <th scope="col">Company</th>
                  <th scope="col">Entry date</th>
                  <th scope="col">Quantity</th>
                  <th scope="col">Avg entry</th>
                  <th scope="col">Current price</th>
                  <th scope="col">Cost basis</th>
                  <th scope="col">Current value</th>
                  <th scope="col">Unrealized P&amp;L</th>
                  <th scope="col">Unrealized return</th>
                  <th scope="col">Currency</th>
                  <th scope="col">Fees</th>
                  <th scope="col">Status</th>
                  <th scope="col">Closed</th>
                  <th scope="col">Notes</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((position) => (
                  <tr key={position.id}>
                    <td>{position.ticker}</td>
                    <td>{position.name}</td>
                    <td>{formatDate(position.entry_date)}</td>
                    <td>{formatNum(position.quantity, 4)}</td>
                    <td>{formatPrice(position.average_entry_price, position.currency)}</td>
                    <td>
                      {formatDisplayPrice(position.current_price, position.price_currency)}
                      {position.price_date && (
                        <span className="date-hint">{formatDate(position.price_date)}</span>
                      )}
                    </td>
                    <td>{formatDisplayPrice(position.cost_basis, position.currency)}</td>
                    <td>{formatDisplayPrice(position.current_value, position.currency)}</td>
                    <td className={displayClass(position.unrealized_gain_loss)}>
                      {formatDisplayPrice(position.unrealized_gain_loss, position.currency)}
                    </td>
                    <td className={displayClass(position.unrealized_return_pct)}>
                      {formatDisplayPercent(position.unrealized_return_pct)}
                    </td>
                    <td>{position.currency}</td>
                    <td>{formatPrice(position.fees, position.currency)}</td>
                    <td>{statusLabel(position.status)}</td>
                    <td>{formatDate(position.closed_at)}</td>
                    <td>{position.notes || "-"}</td>
                    <td className="positions-table__actions">
                      <button
                        type="button"
                        className="positions-btn positions-btn--ghost"
                        onClick={() => handleEdit(position)}
                      >
                        Edit
                      </button>
                      {position.status === "active" && (
                        <button
                          type="button"
                          className="positions-btn positions-btn--ghost"
                          onClick={() => handleClose(position.id)}
                          disabled={closingId === position.id}
                        >
                          {closingId === position.id ? "Closing..." : "Close"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <section className="positions-snapshots" aria-labelledby="entry-snapshot-title">
            <div className="positions-panel__header">
              <h2 id="entry-snapshot-title" className="positions-panel__title">
                Entry snapshots
              </h2>
            </div>
            <div className="positions-snapshots__grid">
              {positions.map((position) => {
                const profile = profileMap.get(position.id);
                return (
                  <article key={`${position.id}-profile`} className="positions-snapshot-card">
                    <div className="positions-snapshot-card__header">
                      <h3 className="positions-snapshot-card__title">
                        {position.ticker} - {position.name}
                      </h3>
                      <span className="positions-snapshot-card__date">
                        Snapshot: {formatDate(profile?.snapshot_taken_at ?? null)}
                      </span>
                    </div>

                    {!profile ? (
                      <p className="page-state__hint">
                        No entry profile captured yet for this position.
                      </p>
                    ) : (
                      <>
                        <section className="positions-snapshot-card__section" aria-label="Entry thesis">
                          <h4 className="positions-snapshot-card__section-title">Entry thesis</h4>
                          <div className="detail-grid">
                            <div className="detail-grid__item detail-grid__item--full">
                              <span className="detail-grid__label">Thesis summary</span>
                              <span className="detail-grid__value detail-grid__value--wrap">
                                {formatDisplayText(profile.thesis_summary)}
                              </span>
                            </div>
                            <div className="detail-grid__item detail-grid__item--full">
                              <span className="detail-grid__label">Why I bought</span>
                              <span className="detail-grid__value detail-grid__value--wrap">
                                {formatDisplayText(profile.why_bought)}
                              </span>
                            </div>
                            <div className="detail-grid__item detail-grid__item--full">
                              <span className="detail-grid__label">Key risks</span>
                              <span className="detail-grid__value detail-grid__value--wrap">
                                {formatDisplayText(profile.key_risks)}
                              </span>
                            </div>
                            <div className="detail-grid__item">
                              <span className="detail-grid__label">Target price</span>
                              <span className="detail-grid__value">
                                {formatDisplayPrice(profile.target_price, profile.target_price_currency)}
                              </span>
                            </div>
                            <div className="detail-grid__item">
                              <span className="detail-grid__label">Holding period</span>
                              <span className="detail-grid__value">
                                {formatDisplayText(profile.expected_holding_period)}
                              </span>
                            </div>
                            <div className="detail-grid__item">
                              <span className="detail-grid__label">Confidence</span>
                              <span className="detail-grid__value">
                                {formatStatusText(profile.confidence_level)}
                              </span>
                            </div>
                            <div className="detail-grid__item detail-grid__item--full">
                              <span className="detail-grid__label">Catalysts</span>
                              <span className="detail-grid__value detail-grid__value--wrap">
                                {formatDisplayText(profile.catalysts)}
                              </span>
                            </div>
                            <div className="detail-grid__item detail-grid__item--full">
                              <span className="detail-grid__label">Invalidation criteria</span>
                              <span className="detail-grid__value detail-grid__value--wrap">
                                {formatDisplayText(profile.invalidation_criteria)}
                              </span>
                            </div>
                          </div>
                        </section>

                        <div className="positions-snapshot-card__divider" />

                        <section className="positions-snapshot-card__section" aria-label="Entry and current comparison">
                          <h4 className="positions-snapshot-card__section-title">Entry vs current</h4>
                          <div className="positions-comparison">
                            <div className="positions-comparison__header">Metric</div>
                            <div className="positions-comparison__header">At entry</div>
                            <div className="positions-comparison__header">Current</div>

                            <div className="positions-comparison__label">Price</div>
                            <div className="positions-comparison__value">
                              {formatPriceWithDate(
                                profile.entry_price,
                                profile.entry_price_currency,
                                profile.entry_price_date,
                              )}
                            </div>
                            <div className="positions-comparison__value">
                              {formatPriceWithDate(
                                position.current_price,
                                position.price_currency,
                                position.price_date,
                              )}
                            </div>

                            <div className="positions-comparison__label">Signal</div>
                            <div className="positions-comparison__value">
                              {formatStatusText(profile.entry_signal)}
                            </div>
                            <div className="positions-comparison__value">
                              {formatStatusText(position.current_signal)}
                            </div>

                            <div className="positions-comparison__label">Readiness</div>
                            <div className="positions-comparison__value">
                              {formatStatusText(profile.entry_readiness_status)}
                            </div>
                            <div className="positions-comparison__value">
                              {formatStatusText(position.current_readiness_status)}
                            </div>

                            <div className="positions-comparison__label">Data quality</div>
                            <div className="positions-comparison__value">
                              {formatStatusText(profile.entry_data_quality_status)}
                            </div>
                            <div className="positions-comparison__value">
                              {formatStatusText(position.current_data_quality_status)}
                            </div>

                            <div className="positions-comparison__label">Quality score</div>
                            <div className="positions-comparison__value">
                              {profile.entry_quality_score != null
                                ? formatNum(profile.entry_quality_score, 1)
                                : "-"}
                            </div>
                            <div className="positions-comparison__value">
                              {position.current_quality_score != null
                                ? formatNum(position.current_quality_score, 1)
                                : "-"}
                            </div>

                            <div className="positions-comparison__label">Valuation range</div>
                            <div className="positions-comparison__value">
                              {formatValuationRange(
                                profile.entry_valuation_low,
                                profile.entry_valuation_mid,
                                profile.entry_valuation_high,
                                profile.entry_price_currency,
                              )}
                            </div>
                            <div className="positions-comparison__value">
                              {formatValuationRange(
                                position.current_valuation_low,
                                position.current_valuation_mid,
                                position.current_valuation_high,
                                position.price_currency ?? position.currency,
                              )}
                            </div>

                            <div className="positions-comparison__label">Margin of safety</div>
                            <div className="positions-comparison__value">
                              {formatDisplayPercent(profile.entry_margin_of_safety)}
                            </div>
                            <div className="positions-comparison__value">
                              {formatDisplayPercent(position.current_margin_of_safety)}
                            </div>
                          </div>
                        </section>

                        <div className="positions-snapshot-card__divider" />

                        <section className="positions-snapshot-card__section" aria-label="Frozen entry snapshot details">
                          <h4 className="positions-snapshot-card__section-title">Frozen entry snapshot</h4>
                          <div className="detail-grid">
                            <div className="detail-grid__item">
                              <span className="detail-grid__label">Entry price currency</span>
                              <span className="detail-grid__value">
                                {formatDisplayText(profile.entry_price_currency)}
                              </span>
                            </div>
                            <div className="detail-grid__item">
                              <span className="detail-grid__label">Entry uncertainty</span>
                              <span className="detail-grid__value">
                                {formatStatusText(profile.entry_uncertainty_category)}
                              </span>
                            </div>
                            <div className="detail-grid__item">
                              <span className="detail-grid__label">Current uncertainty</span>
                              <span className="detail-grid__value">
                                {formatStatusText(position.current_uncertainty_category)}
                              </span>
                            </div>
                          </div>
                        </section>
                      </>
                    )}
                  </article>
                );
              })}
            </div>
          </section>
        </>
      )}

      <p className="page__footer-note">
        Positions are manual recordkeeping only in Phase 12C. Entry snapshots are
        stored reference points and do not modify watchlist analytics, readiness,
        valuation, or signal output.
      </p>
    </div>
  );
}
