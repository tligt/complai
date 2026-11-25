-- D-217, 25 Nov: an account can be blocked (fraud, a payment with a stolen
-- card…). 'blocked' joins the account statuses; account_periods takes any
-- status (no check there). The reason goes in the period's note, as every
-- status change does. Idempotent.

alter table public.accounts drop constraint if exists accounts_status_check;
alter table public.accounts add constraint accounts_status_check
    check (status in ('registered', 'trial', 'active', 'expired', 'cancelled', 'blocked'));

notify pgrst, 'reload schema';
