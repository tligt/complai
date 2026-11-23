-- S74 — yearly plans: the billing cycle of an account (23 Nov 2026)
--
-- Each plan is sold per month or per year; a year costs 11 months
-- (pricing.py). The cycle is recorded on the account and, like the plan and
-- status, in each dated period (account_periods), so a yearly term has a
-- start date to count the year from. NULL = not chosen yet (trials,
-- invitations, accounts from before S74).
--
-- Run once (psql -1, ON_ERROR_STOP), then NOTIFY pgrst, 'reload schema'.

ALTER TABLE accounts ADD COLUMN IF NOT EXISTS billing_cycle text
    CHECK (billing_cycle IN ('monthly', 'yearly'));
ALTER TABLE account_periods ADD COLUMN IF NOT EXISTS billing_cycle text
    CHECK (billing_cycle IN ('monthly', 'yearly'));
