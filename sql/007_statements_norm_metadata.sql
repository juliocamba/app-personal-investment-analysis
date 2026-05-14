-- 007_statements_norm_metadata.sql
-- Phase 10A: add metadata jsonb column to statements_norm for provider
-- provenance, fallback reasons, and per-field SEC concept attribution.
--
-- Migration is additive only (add column if not exists) — safe to run
-- multiple times.  No RLS changes.  No uniqueness changes.

alter table statements_norm
  add column if not exists metadata jsonb not null default '{}'::jsonb;
