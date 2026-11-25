-- D-212, 25 Nov: lifecycle emails (onboarding first; then trial ending,
-- expired trial, payments, churned — the five flows agreed on 25 Nov).
--
-- lifecycle_emails: one row per email sent to an account, so nothing goes out
-- twice and the back office can show who got what. `detail` says which
-- variant went out (for onboarding's step emails: the step it was about).
--
-- profiles.lifecycle_emails_off_at: the person used the "stop these emails"
-- link. Onboarding and win-back emails stop; payment and deletion warnings,
-- which concern the service itself, do not.
--
-- Service role only: written by monitor_onboarding.py and read by the back
-- office. Idempotent.

create table if not exists public.lifecycle_emails (
    id          bigint generated always as identity primary key,
    account_id  uuid not null references public.accounts(id) on delete cascade,
    user_id     uuid not null,
    flow        text not null,
    email_key   text not null,
    detail      text,
    sent_at     timestamptz not null default now(),
    unique (account_id, flow, email_key)
);
create index if not exists lifecycle_emails_account_idx on public.lifecycle_emails (account_id, sent_at);
alter table public.lifecycle_emails enable row level security;

alter table public.profiles add column if not exists lifecycle_emails_off_at timestamptz;

notify pgrst, 'reload schema';
