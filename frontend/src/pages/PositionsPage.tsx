import React, { useEffect, useMemo, useState } from "react";
import {
  closePosition,
  createPosition,
  fetchCompaniesForPositions,
  fetchPositions,
  updatePosition,
} from "../lib/api";
import { formatDate, formatPrice, formatNum } from "../lib/formatters";
import type { CompanyOption, PositionInput, PositionRow } from "../types";

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
};

function statusLabel(status: PositionRow["status"]): string {
  return status === "active" ? "Active" : "Closed";
}

function buildPayload(form: PositionFormState): PositionInput {
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

export function PositionsPage() {
  const [positions, setPositions] = useState<PositionRow[]>([]);
  const [companies, setCompanies] = useState<CompanyOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [closingId, setClosingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<PositionFormState>(EMPTY_FORM);

  useEffect(() => {
    Promise.all([fetchPositions(), fetchCompaniesForPositions()])
      .then(([positionRows, companyRows]) => {
        setPositions(positionRows);
        setCompanies(companyRows);
        if (companyRows.length > 0) {
          setForm((prev) => ({
            ...prev,
            company_id: prev.company_id || companyRows[0].id,
            currency: prev.currency || companyRows[0].currency || "USD",
          }));
        }
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

  function resetForm(nextCompanies = companies): void {
    setEditingId(null);
    setSaveError(null);
    setForm({
      ...EMPTY_FORM,
      company_id: nextCompanies[0]?.id ?? "",
      currency: nextCompanies[0]?.currency ?? "USD",
    });
  }

  function handleCompanyChange(companyId: string): void {
    const selected = companyMap.get(companyId);
    setForm((prev) => ({
      ...prev,
      company_id: companyId,
      currency: selected?.currency ?? prev.currency,
    }));
  }

  function handleEdit(position: PositionRow): void {
    setEditingId(position.id);
    setSaveError(null);
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
    });
  }

  function upsertLocalPosition(next: PositionRow): void {
    setPositions((prev) => {
      const existing = prev.some((row) => row.id === next.id);
      const updated = existing
        ? prev.map((row) => (row.id === next.id ? next : row))
        : [next, ...prev];
      return updated.sort((a, b) => {
        if (a.status !== b.status) {
          return a.status === "active" ? -1 : 1;
        }
        return a.entry_date < b.entry_date ? 1 : -1;
      });
    });
  }

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setIsSaving(true);
    setSaveError(null);
    try {
      const payload = buildPayload(form);
      const saved = editingId
        ? await updatePosition(editingId, payload)
        : await createPosition(payload);
      upsertLocalPosition(saved);
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
      const saved = await closePosition(positionId);
      upsertLocalPosition(saved);
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
        <div className="spinner" aria-label="Loading positions…" />
        <p>Loading positions…</p>
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
            <button type="button" className="positions-btn positions-btn--ghost" onClick={() => resetForm()}>
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
                  {company.ticker} — {company.name}
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

          <div className="positions-form__actions">
            <button type="submit" className="positions-btn" disabled={isSaving || companies.length === 0}>
              {isSaving ? "Saving…" : editingId ? "Save changes" : "Add position"}
            </button>
          </div>
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
        <div className="table-wrapper">
          <table className="positions-table" aria-label="Manual positions">
            <thead>
              <tr>
                <th scope="col">Ticker</th>
                <th scope="col">Company</th>
                <th scope="col">Entry date</th>
                <th scope="col">Quantity</th>
                <th scope="col">Avg entry</th>
                <th scope="col">Currency</th>
                <th scope="col">Fees</th>
                <th scope="col">Status</th>
                <th scope="col">Closed</th>
                <th scope="col">Notes</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((position) => {
                const company = companyMap.get(position.company_id);
                return (
                  <tr key={position.id}>
                    <td>{company?.ticker ?? "Unknown"}</td>
                    <td>{company?.name ?? "Unknown company"}</td>
                    <td>{formatDate(position.entry_date)}</td>
                    <td>{formatNum(position.quantity, 4)}</td>
                    <td>{formatPrice(position.average_entry_price, position.currency)}</td>
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
                          {closingId === position.id ? "Closing…" : "Close"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="page__footer-note">
        Positions are manual recordkeeping only in Phase 12B. They do not modify
        watchlist analytics, readiness, valuation, or signal output.
      </p>
    </div>
  );
}
