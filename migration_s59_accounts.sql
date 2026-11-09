-- S59 (D-151, D-152): customer accounts and subscription history.
--
-- The plan, status and trial move from the person (profiles) to a customer
-- account — the contracting party — with its companies under it. Every
-- change is a dated period in account_periods, append-only: a period is
-- only ever closed (ends_at set once), never edited or deleted.
--
-- Written only with the service role (back office, sign-up, trial). Read by
-- the account's owner and, read-only, by the people of its companies.

-- ── Accounts ─────────────────────────────────────────────────────────────
create table if not exists public.accounts (
    id              uuid primary key default gen_random_uuid(),
    name            text not null,
    plan            text not null default 'professional'
                    check (plan in ('starter', 'professional', 'advisory', 'enterprise')),
    status          text not null default 'registered'
                    check (status in ('registered', 'trial', 'active', 'expired', 'cancelled')),
    trial_ends_at   timestamptz,
    -- The person who manages it in the app. One account per owner: every
    -- company a person creates goes into their account.
    owner_user_id   uuid unique references auth.users (id) on delete set null,
    -- The contract contact, typed in by an admin; may have no login.
    contact_name    text,
    contact_email   text,
    contact_phone   text,
    contact_user_id uuid references auth.users (id) on delete set null,
    billing_email   text,
    vat_number      text,
    notes           text,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

comment on table public.accounts is
  'S59: the customer (contracting party): plan, status, trial, contract contact. Companies via clients.account_id.';

-- ── History ──────────────────────────────────────────────────────────────
create table if not exists public.account_periods (
    id             uuid primary key default gen_random_uuid(),
    account_id     uuid not null references public.accounts (id) on delete cascade,
    plan           text not null,
    status         text not null,
    trial_ends_at  timestamptz,
    starts_at      timestamptz not null default now(),
    ends_at        timestamptz,                 -- null: the current period
    note           text,
    changed_by     uuid references auth.users (id) on delete set null,
    created_at     timestamptz not null default now()
);

create index if not exists account_periods_account_idx
    on public.account_periods (account_id, starts_at desc);
create unique index if not exists account_periods_one_open
    on public.account_periods (account_id) where ends_at is null;

-- Append-only: no delete; an update may only close an open period.
create or replace function public.account_periods_append_only()
returns trigger language plpgsql set search_path = public as $$
begin
    if tg_op = 'DELETE' then
        -- Allowed only when the account itself is being deleted (cascade).
        if exists (select 1 from public.accounts where id = old.account_id) then
            raise exception 'account_periods is append-only';
        end if;
        return old;
    end if;
    if old.ends_at is not null
       or new.ends_at is null
       or (new.account_id, new.plan, new.status, new.trial_ends_at, new.starts_at,
           new.note, new.changed_by, new.created_at)
          is distinct from
          (old.account_id, old.plan, old.status, old.trial_ends_at, old.starts_at,
           old.note, old.changed_by, old.created_at) then
        raise exception 'account_periods is append-only: a period can only be closed';
    end if;
    return new;
end $$;

drop trigger if exists account_periods_no_change on public.account_periods;
create trigger account_periods_no_change
    before update or delete on public.account_periods
    for each row execute function public.account_periods_append_only();

-- ── Companies belong to an account ──────────────────────────────────────
alter table public.clients
    add column if not exists account_id uuid references public.accounts (id) on delete set null;
create index if not exists clients_account_idx on public.clients (account_id);

-- A new company goes into its creator's account, whatever path created it.
create or replace function public.clients_set_account()
returns trigger language plpgsql security definer set search_path = public as $$
begin
    if new.account_id is null then
        select id into new.account_id from public.accounts where owner_user_id = new.user_id;
    end if;
    return new;
end $$;

-- Trigger functions only: not callable through the API.
revoke execute on function public.clients_set_account() from public, anon, authenticated;
revoke execute on function public.account_periods_append_only() from public, anon, authenticated;

drop trigger if exists clients_set_account on public.clients;
create trigger clients_set_account
    before insert on public.clients
    for each row execute function public.clients_set_account();

-- ── Access ───────────────────────────────────────────────────────────────
alter table public.accounts enable row level security;
alter table public.account_periods enable row level security;
revoke all on public.accounts, public.account_periods from anon;
revoke insert, update, delete on public.accounts, public.account_periods from authenticated;
grant select on public.accounts, public.account_periods to authenticated;

drop policy if exists accounts_read on public.accounts;
create policy accounts_read on public.accounts for select to authenticated using (
    owner_user_id = (select auth.uid())
    or exists (select 1 from public.clients c
               where c.account_id = accounts.id and public.client_role(c.id) is not null)
);

drop policy if exists account_periods_read on public.account_periods;
create policy account_periods_read on public.account_periods for select to authenticated using (
    exists (select 1 from public.accounts a where a.id = account_periods.account_id)
);

-- ── Migration of today's data (9 Nov: six accounts, all RECOSA tests) ────
-- One account per person who owns companies or signed up themselves;
-- invited people get none. Named after their only company, or their email
-- domain (a consultant's account is not named after one of its clients).
insert into public.accounts (name, plan, status, trial_ends_at, owner_user_id, created_at)
select
    coalesce(
        (select min(c.company_name) from public.clients c where c.user_id = p.id
         having count(*) = 1),
        split_part(p.email, '@', 2)),
    coalesce(nullif(p.subscription_tier, ''), 'professional'),
    coalesce(nullif(p.subscription_status, ''), 'registered'),
    case when p.subscription_status = 'trial' then p.trial_ends_at end,
    p.id,
    p.created_at
from public.profiles p
where (exists (select 1 from public.clients c where c.user_id = p.id)
       or coalesce(p.signup_source, '') <> 'invite')
  and not exists (select 1 from public.accounts a where a.owner_user_id = p.id);

update public.clients c set account_id = a.id
from public.accounts a
where a.owner_user_id = c.user_id and c.account_id is null;

insert into public.account_periods (account_id, plan, status, trial_ends_at, starts_at, note)
select a.id, a.plan, a.status, a.trial_ends_at, a.created_at, 'Carried over from the person''s plan (S59 migration)'
from public.accounts a
where not exists (select 1 from public.account_periods ap where ap.account_id = a.id);
