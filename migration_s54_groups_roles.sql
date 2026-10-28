-- S54 — Enterprise groups, roles per company, and a full audit trail.
-- Applied 28 Oct 2026 through the Supabase MCP server.
--
-- Roles: admin (people, roles, settings + all of contributor), contributor
-- (the compliance work), read_only (sees everything, changes nothing). The
-- owner of a company (clients.user_id) is always admin on it.
--
-- A group is one Enterprise owner's account: every company that owner owns
-- belongs to it. A group member gets their role on all of them, including
-- companies added later.

-- ── Roles on the existing per-company membership (S38) ────────────────
-- Existing members keep what they had: full access to the data, no team
-- management. That is contributor.
alter table workspace_members
  add column if not exists role text not null default 'contributor';
alter table workspace_members drop constraint if exists workspace_members_role_check;
alter table workspace_members
  add constraint workspace_members_role_check
  check (role in ('admin', 'contributor', 'read_only'));

-- ── Groups ────────────────────────────────────────────────────────────
create table if not exists client_groups (
  id            uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null unique references auth.users(id) on delete cascade,
  name          text not null check (btrim(name) <> ''),
  created_at    timestamptz not null default now()
);

create table if not exists group_members (
  id             uuid primary key default gen_random_uuid(),
  group_id       uuid not null references client_groups(id) on delete cascade,
  member_user_id uuid references auth.users(id) on delete cascade,
  invited_email  text not null,
  invited_by     uuid not null references auth.users(id),
  role           text not null default 'contributor'
                 check (role in ('admin', 'contributor', 'read_only')),
  status         text not null default 'pending' check (status in ('pending', 'active')),
  created_at     timestamptz not null default now(),
  activated_at   timestamptz,
  unique (group_id, invited_email)
);
create index if not exists group_members_member_idx on group_members (member_user_id);

alter table client_groups enable row level security;
alter table group_members enable row level security;

-- ── Access functions ──────────────────────────────────────────────────
-- SECURITY DEFINER, like has_client_access/is_client_member before them:
-- they read clients and the membership tables without going back through
-- those tables' own policies (the recursion D-103 ran into).

-- The caller's role on one company: 'admin', 'contributor', 'read_only',
-- or NULL for no access. The strongest of owner, company membership and
-- group membership.
create or replace function public.client_role(_client_id uuid)
returns text language sql stable security definer set search_path = public as $$
  select case
    when exists (select 1 from clients where id = _client_id and user_id = auth.uid())
      then 'admin'
    else (
      select r from (
        select wm.role as r from workspace_members wm
         where wm.client_id = _client_id and wm.member_user_id = auth.uid()
           and wm.status = 'active'
        union all
        select gm.role from group_members gm
          join client_groups g on g.id = gm.group_id
          join clients c on c.user_id = g.owner_user_id
         where c.id = _client_id and gm.member_user_id = auth.uid()
           and gm.status = 'active'
      ) x
      order by case r when 'admin' then 1 when 'contributor' then 2 else 3 end
      limit 1)
  end;
$$;

-- Read access. Same signature and NULL-client rule as before, so every
-- SELECT policy keeps working unchanged.
create or replace function public.has_client_access(_client_id uuid, _row_user_id uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select case
    when _client_id is null then _row_user_id = auth.uid()
    else public.client_role(_client_id) is not null
  end;
$$;

-- Write access: admin or contributor. Read-only is refused here, in the
-- database, not by hiding buttons (D-06, D-62).
create or replace function public.can_edit_client(_client_id uuid, _row_user_id uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select case
    when _client_id is null then _row_user_id = auth.uid()
    else coalesce(public.client_role(_client_id) in ('admin', 'contributor'), false)
  end;
$$;

create or replace function public.is_client_admin(_client_id uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select coalesce(public.client_role(_client_id) = 'admin', false);
$$;

-- Used by clients' own SELECT policy: access through a membership (company
-- or group). Never reads clients through RLS, so INSERT ... RETURNING on
-- clients still sees its own row through the owner branch (D-103, bug 2).
create or replace function public.is_client_member(_client_id uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from workspace_members
     where client_id = _client_id and member_user_id = auth.uid() and status = 'active'
  ) or exists (
    select 1 from group_members gm
      join client_groups g on g.id = gm.group_id
      join clients c on c.user_id = g.owner_user_id
     where c.id = _client_id and gm.member_user_id = auth.uid() and gm.status = 'active'
  );
$$;

create or replace function public.group_role(_group_id uuid)
returns text language sql stable security definer set search_path = public as $$
  select case
    when exists (select 1 from client_groups where id = _group_id and owner_user_id = auth.uid())
      then 'admin'
    else (select role from group_members
           where group_id = _group_id and member_user_id = auth.uid() and status = 'active'
           limit 1)
  end;
$$;

-- ── Write policies: contributor or admin ──────────────────────────────
-- Every INSERT/UPDATE/DELETE policy on compliance data swaps
-- has_client_access for can_edit_client; the arguments stay the same.
-- Left on read access on purpose: a read-only user may still ask the
-- Assistant, rate an answer, mark an alert read and open a support ticket
-- (chat_history, answer_feedback, client_alerts, support_tickets).
do $$
declare
  p record;
  stmt text;
begin
  for p in
    select tablename, policyname, cmd, qual, with_check from pg_policies
     where schemaname = 'public'
       and cmd in ('INSERT', 'UPDATE', 'DELETE')
       and tablename not in ('chat_history', 'answer_feedback', 'client_alerts',
                             'support_tickets', 'task_events')
       and (coalesce(qual, '') like '%has_client_access(%'
            or coalesce(with_check, '') like '%has_client_access(%')
  loop
    stmt := format('alter policy %I on public.%I', p.policyname, p.tablename);
    if p.qual is not null then
      stmt := stmt || ' using (' || replace(p.qual, 'has_client_access(', 'can_edit_client(') || ')';
    end if;
    if p.with_check is not null then
      stmt := stmt || ' with check (' || replace(p.with_check, 'has_client_access(', 'can_edit_client(') || ')';
    end if;
    execute stmt;
  end loop;
end $$;

-- task_events: the register writes 'opened'/'closed' itself whenever anyone
-- looks at it (obligation_store.reconcile), read-only users included — the
-- history must stay true. Decisions (dismissed, assigned, noted) need edit.
alter policy task_events_insert on public.task_events with check (
  user_id = auth.uid()
  and has_client_access(client_id, user_id)
  and (event in ('opened', 'closed') or can_edit_client(client_id, user_id))
);

-- The company profile: contributors and admins edit, read-only does not.
-- Deleting a company stays the owner's alone.
alter policy "Users can update own clients" on public.clients
  using ((auth.uid() = user_id) or can_edit_client(id, user_id))
  with check ((auth.uid() = user_id) or can_edit_client(id, user_id));

-- ── Team management: admins ───────────────────────────────────────────
-- Everyone with access sees who else has access; admins invite, change
-- roles and remove; anyone can leave.
drop policy if exists workspace_members_select on workspace_members;
create policy workspace_members_select on workspace_members for select
  using (member_user_id = auth.uid() or client_role(client_id) is not null);
drop policy if exists workspace_members_insert on workspace_members;
create policy workspace_members_insert on workspace_members for insert
  with check (is_client_admin(client_id));
drop policy if exists workspace_members_update on workspace_members;
create policy workspace_members_update on workspace_members for update
  using (is_client_admin(client_id)) with check (is_client_admin(client_id));
drop policy if exists workspace_members_delete on workspace_members;
create policy workspace_members_delete on workspace_members for delete
  using (member_user_id = auth.uid() or is_client_admin(client_id));

create policy client_groups_select on client_groups for select
  using (group_role(id) is not null);
create policy client_groups_insert on client_groups for insert
  with check (owner_user_id = auth.uid());
create policy client_groups_update on client_groups for update
  using (group_role(id) = 'admin') with check (group_role(id) = 'admin');

create policy group_members_select on group_members for select
  using (member_user_id = auth.uid() or group_role(group_id) is not null);
create policy group_members_insert on group_members for insert
  with check (group_role(group_id) = 'admin');
create policy group_members_update on group_members for update
  using (group_role(group_id) = 'admin') with check (group_role(group_id) = 'admin');
create policy group_members_delete on group_members for delete
  using (member_user_id = auth.uid() or group_role(group_id) = 'admin');

-- UPDATE: read access in USING, edit access in WITH CHECK. With edit access
-- in USING, a read-only user's update matched no row and succeeded silently,
-- so the page said "Saved". This way it fails with 42501 and the page shows
-- the error. (Applied as a second migration, s54_update_refuses_loudly.)
do $$
declare p record;
begin
  for p in
    select tablename, policyname, qual from pg_policies
     where schemaname = 'public' and cmd = 'UPDATE'
       and coalesce(qual, '') like '%can_edit_client(%'
       and tablename <> 'clients'
  loop
    execute format('alter policy %I on public.%I using (%s)', p.policyname, p.tablename,
                   replace(p.qual, 'can_edit_client(', 'has_client_access('));
  end loop;
end $$;

alter policy "Users can update own clients" on public.clients
  using ((auth.uid() = user_id) or is_client_member(id))
  with check ((auth.uid() = user_id) or can_edit_client(id, user_id));

-- ── Audit trail ───────────────────────────────────────────────────────
-- Everyone with access to a company reads its trail (a group member reads
-- every company of the group). Nobody writes it directly: rows come only
-- from log_audit_event() with the service role.
drop policy if exists clients_view_own_audit_log on audit_log;
create policy clients_view_own_audit_log on audit_log for select
  using (client_role(company_id) is not null);

-- Append-only for everyone, the service role included: no edit, no delete.
-- S51 (GDPR deletion) will have to decide how a company's trail ends when the
-- company is deleted; it does that deliberately, by changing this trigger.
create or replace function public.audit_log_immutable()
returns trigger language plpgsql as $$
begin
  raise exception 'audit_log is append-only: % refused', tg_op;
end;
$$;
drop trigger if exists audit_log_no_change on audit_log;
create trigger audit_log_no_change before update or delete on audit_log
  for each row execute function public.audit_log_immutable();
alter function public.audit_log_immutable() set search_path = public;

-- ── Refused deletes fail loudly (s54_delete_refuses_loudly) ───────────
-- With edit access in a DELETE policy's USING, a read-only user's delete
-- matched no row and the page reported success. USING now grants read
-- access and a trigger refuses the row with 42501 and a plain sentence.
-- Only for the API's authenticated role: the service role and cascades
-- (run as the table owner) are not affected.
create or replace function public.enforce_client_edit_on_delete()
returns trigger language plpgsql set search_path = public as $$
begin
  if current_user = 'authenticated' and not can_edit_client(old.client_id, old.user_id) then
    raise exception using errcode = '42501',
      message = 'You have read-only access to this company: changes are not saved.';
  end if;
  return old;
end;
$$;

do $$
declare p record;
begin
  for p in
    select tablename, policyname, qual from pg_policies
     where schemaname = 'public' and cmd = 'DELETE'
       and coalesce(qual, '') like '%can_edit_client(%'
  loop
    execute format('alter policy %I on public.%I using (%s)', p.policyname, p.tablename,
                   replace(p.qual, 'can_edit_client(', 'has_client_access('));
    execute format('drop trigger if exists %I on public.%I', p.tablename || '_edit_on_delete', p.tablename);
    execute format('create trigger %I before delete on public.%I for each row execute function public.enforce_client_edit_on_delete()',
                   p.tablename || '_edit_on_delete', p.tablename);
  end loop;
end $$;
