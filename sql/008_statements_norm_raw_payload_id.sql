-- 008_statements_norm_raw_payload_id.sql
-- Phase 10A: add raw_payload_id FK to statements_norm for SEC fallback traceability.
-- Additive, idempotent.  Mirrors the same column found on news_events and other
-- tables so every normalized row can be traced back to its raw provider response.

alter table statements_norm
  add column if not exists raw_payload_id uuid references raw_provider_payloads(id) on delete set null;
