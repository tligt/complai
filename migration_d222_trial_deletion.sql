-- D-222, 27 Nov: an expired trial loses access on day 45 and is deleted on
-- day 60 (agreed with the user on 27 Nov). See expired_trial.py.
--
-- accounts.access_closes_at / delete_after: fixed when the first notice is
-- emailed, so the app, the emails and the deletion read the same dates and
-- nobody is closed or deleted without notice.
--
-- email_suppressions: addresses that asked to stop our emails, kept after
-- the account is deleted (the privacy policy says so). No foreign key.
--
-- account_deletion_files(account): the stored files to remove first (the
-- storage API removes them; deleting storage.objects rows would not). It
-- runs the same checks (assert_trial_deletable) first, so a refused account
-- loses no file.
-- delete_trial_account(account): everything else, in one transaction. It
-- refuses an account that is not an expired trial past its delete_after,
-- one that ever had a paid or active period, an admin's, or one with a
-- document under legal hold. Kept on purpose: terms_acceptances (D-221),
-- email_suppressions. Deleted with it: the companies the account owns and
-- everything in them (members lose access to them), the owner's sign-in and
-- profile, their free-check leads, support requests, logs and history.
--
-- The audit trail (D-128: append-only for everyone, "until the deletion
-- decides how a deleted company's trail ends"): it ends with the company.
-- audit_log_immutable() now lets a DELETE through only inside
-- delete_trial_account's own transaction (a transaction-local setting it
-- sets), and only for that account's rows. UPDATE stays refused, and DELETE
-- from anywhere else too.
--
-- Service role only (security definer, execute revoked from the API roles).
-- Idempotent.

create or replace function public.audit_log_immutable()
returns trigger language plpgsql set search_path = public as $$
declare
  acct  text := nullif(current_setting('recosa.deleting_account', true), '');
  owner uuid;
begin
  if tg_op = 'DELETE' and acct is not null then
    owner := nullif(current_setting('recosa.deleting_owner', true), '')::uuid;
    if old.user_id = owner
       or old.company_id in (select id from public.clients
                             where account_id = acct::uuid or user_id = owner) then
      return old;
    end if;
  end if;
  raise exception 'audit_log is append-only: % refused', tg_op;
end;
$$;

alter table public.accounts add column if not exists access_closes_at timestamptz;
alter table public.accounts add column if not exists delete_after timestamptz;

create table if not exists public.email_suppressions (
    email      text primary key,
    reason     text not null,
    created_at timestamptz not null default now()
);
alter table public.email_suppressions enable row level security;

-- The checks, shared: a refused account is refused before any file goes.
create or replace function public.assert_trial_deletable(p_account uuid)
returns void
language plpgsql security definer set search_path = public
as $$
declare
    acc public.accounts%rowtype;
begin
    select * into acc from public.accounts where id = p_account;
    if not found then
        raise exception 'account % not found', p_account;
    end if;
    if acc.status <> 'expired' or acc.delete_after is null or acc.delete_after > now() then
        raise exception 'account % is not an expired trial due for deletion', p_account;
    end if;
    if exists (select 1 from public.account_periods
               where account_id = p_account and status not in ('trial', 'expired', 'registered')) then
        raise exception 'account % had a plan: not a trial deletion', p_account;
    end if;
    if exists (select 1 from public.profiles where id = acc.owner_user_id and role = 'admin') then
        raise exception 'account % belongs to an admin', p_account;
    end if;
    if exists (select 1 from public.client_documents d join public.clients c on c.id = d.client_id
               where (c.account_id = p_account or c.user_id = acc.owner_user_id) and d.legal_hold) then
        raise exception 'account % has a document under legal hold', p_account;
    end if;
end;
$$;

create or replace function public.account_deletion_files(p_account uuid)
returns table(bucket text, name text)
language plpgsql security definer set search_path = public, storage
as $$
begin
    perform public.assert_trial_deletable(p_account);
    return query
    with acc as (select owner_user_id from public.accounts where id = p_account),
         cl as (select id::text as id from public.clients
                where account_id = p_account or user_id = (select owner_user_id from acc))
    select o.bucket_id::text, o.name::text
    from storage.objects o
    where o.bucket_id in ('compliance-files', 'audit-reports')
      and (split_part(o.name, '/', 1) = (select owner_user_id::text from acc)
           or split_part(o.name, '/', 2) in (select id from cl));
end;
$$;

create or replace function public.delete_trial_account(p_account uuid)
returns jsonb
language plpgsql security definer set search_path = public, auth
as $$
declare
    acc     public.accounts%rowtype;
    prof    public.profiles%rowtype;
    cids    uuid[];
    n       jsonb := '{}'::jsonb;
    c       int;
begin
    perform public.assert_trial_deletable(p_account);
    select * into acc from public.accounts where id = p_account for update;
    select * into prof from public.profiles where id = acc.owner_user_id;
    select coalesce(array_agg(id), '{}') into cids from public.clients
     where account_id = p_account or user_id = acc.owner_user_id;

    perform set_config('recosa.deleting_account', p_account::text, true);
    perform set_config('recosa.deleting_owner', acc.owner_user_id::text, true);

    if prof.id is not null and prof.lifecycle_emails_off_at is not null and prof.email is not null then
        insert into public.email_suppressions (email, reason)
        values (lower(prof.email), 'stopped the emails, account deleted')
        on conflict (email) do nothing;
    end if;

    -- Rows that would block deleting the companies or the sign-in (no
    -- cascade), or that hold no foreign key at all.
    delete from public.audits where user_id = acc.owner_user_id or client_id = any(cids);
    get diagnostics c = row_count; n := n || jsonb_build_object('audits', c);
    delete from public.audit_log where user_id = acc.owner_user_id or company_id = any(cids);
    get diagnostics c = row_count; n := n || jsonb_build_object('audit_log', c);
    delete from public.client_documents where client_id = any(cids) or user_id = acc.owner_user_id;
    get diagnostics c = row_count; n := n || jsonb_build_object('client_documents', c);
    delete from public.documents where client_id = any(cids) or user_id = acc.owner_user_id;
    get diagnostics c = row_count; n := n || jsonb_build_object('documents', c);
    delete from public.brand_profiles where client_id = any(cids) or user_id = acc.owner_user_id;
    delete from public.obligation_responses where client_id = any(cids) or user_id = acc.owner_user_id;
    delete from public.risk_assessments where client_id = any(cids) or user_id = acc.owner_user_id;
    delete from public.task_events where client_id = any(cids) or user_id = acc.owner_user_id;
    delete from public.invitation_redemptions where user_id = acc.owner_user_id;
    delete from public.workspace_members where invited_by = acc.owner_user_id;
    delete from public.group_members where invited_by = acc.owner_user_id;
    if prof.email is not null then
        delete from public.leads where lower(email) = lower(prof.email);
        get diagnostics c = row_count; n := n || jsonb_build_object('leads', c);
    end if;

    delete from public.clients where id = any(cids);
    get diagnostics c = row_count; n := n || jsonb_build_object('companies', c);
    delete from public.accounts where id = p_account;
    -- The sign-in: cascades to the profile and every row keyed on the user.
    delete from auth.users where id = acc.owner_user_id;
    get diagnostics c = row_count; n := n || jsonb_build_object('users', c);
    return n;
end;
$$;

revoke all on function public.assert_trial_deletable(uuid) from public, anon, authenticated;
revoke all on function public.account_deletion_files(uuid) from public, anon, authenticated;
revoke all on function public.delete_trial_account(uuid) from public, anon, authenticated;
grant execute on function public.assert_trial_deletable(uuid) to service_role;
grant execute on function public.account_deletion_files(uuid) to service_role;
grant execute on function public.delete_trial_account(uuid) to service_role;

notify pgrst, 'reload schema';
