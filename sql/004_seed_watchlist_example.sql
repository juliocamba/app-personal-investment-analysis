-- 004_seed_watchlist_example.sql
-- Example seed data for local development and Supabase testing.
--
-- BEFORE RUNNING: replace 'jbcamba@gmail.com' with your real email address.
--
-- This file is idempotent: re-running it does not create duplicate rows.
-- Run after 001, 002, and 003 have been applied successfully.

insert into app_users (email, display_name)
values ('jbcamba@gmail.com', 'Private Investor')
on conflict (email) do update set display_name = excluded.display_name;

insert into companies (ticker, name, exchange, country, currency, reporting_currency, cik, sector, industry, company_type)
values
  ('AAPL', 'Apple Inc.', 'NASDAQ', 'US', 'USD', 'USD', '0000320193', 'Technology', 'Consumer Electronics', 'non_financial'),
  ('MSFT', 'Microsoft Corporation', 'NASDAQ', 'US', 'USD', 'USD', '0000789019', 'Technology', 'Software', 'non_financial'),
  ('JNJ', 'Johnson & Johnson', 'NYSE', 'US', 'USD', 'USD', '0000200406', 'Healthcare', 'Pharmaceuticals', 'non_financial')
on conflict (ticker, exchange) do update set
  name = excluded.name,
  cik = excluded.cik,
  sector = excluded.sector,
  industry = excluded.industry;

-- Insert the watchlist only if it does not already exist for this user.
insert into watchlists (user_id, name, description)
select u.id, 'Default Watchlist', 'Initial MVP watchlist'
from app_users u
where u.email = 'jbcamba@gmail.com'
  and not exists (
    select 1 from watchlists wl
    where wl.user_id = u.id and wl.name = 'Default Watchlist'
  );

-- Add companies to the watchlist. Idempotent via ON CONFLICT DO NOTHING.
-- Works whether the watchlist was just created or already existed.
insert into watchlist_companies (watchlist_id, company_id, priority)
select wl.id, c.id, 100
from watchlists wl
join app_users u on u.id = wl.user_id
cross join companies c
where u.email = 'jbcamba@gmail.com'
  and wl.name = 'Default Watchlist'
  and c.ticker in ('AAPL', 'MSFT', 'JNJ')
on conflict (watchlist_id, company_id) do nothing;

-- Example alert rules.
-- Idempotent: inserts only when no rule with the same user+company+channel+rule_type exists.
insert into alert_rules (user_id, company_id, channel, rule_type, threshold, enabled, config)
select u.id, c.id, 'telegram', 'p_buy_adjusted_above', 0.70, true, '{}'::jsonb
from app_users u
join companies c on c.ticker in ('AAPL', 'MSFT', 'JNJ')
where u.email = 'jbcamba@gmail.com'
  and not exists (
    select 1 from alert_rules ar
    where ar.user_id = u.id
      and ar.company_id = c.id
      and ar.channel = 'telegram'
      and ar.rule_type = 'p_buy_adjusted_above'
  );
