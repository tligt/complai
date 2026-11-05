-- S56 (D-145): routing and in-app messaging.
--
-- A piece of work — an action-plan task (its finding_key, tasks.py) or an
-- incident (its id) — can be given to one person of the company, either by
-- hand or by the company's routing rule for its area. People discuss it in
-- a comment thread, and get an in-app notification (assignment, comment,
-- mention). D-05: none of this leaves RECOSA; the email is a content-free
-- nudge, sent by the app.
--
-- The work itself is not stored here (tasks are derived on every read,
-- tasks.py): these tables key on (client_id, item_type, item_key).

-- ── Assignments: history, append-only; the newest row per item is current ──
create table if not exists public.assignments (
    id           uuid primary key default gen_random_uuid(),
    client_id    uuid not null references public.clients (id) on delete cascade,
    item_type    text not null check (item_type in ('task', 'incident')),
    item_key     text not null check (char_length(item_key) between 1 and 400),
    item_title   text check (char_length(item_title) <= 300),
    assignee_id  uuid references auth.users (id) on delete set null,   -- null = unassigned
    assigned_by  uuid references auth.users (id) on delete set null,   -- null = a routing rule
    source       text not null default 'manual' check (source in ('manual', 'rule')),
    created_at   timestamptz not null default now()
);
create index if not exists assignments_item_idx
    on public.assignments (client_id, item_type, item_key, created_at desc);
create index if not exists assignments_assignee_idx on public.assignments (assignee_id);

alter table public.assignments enable row level security;
drop policy if exists assignments_select on public.assignments;
create policy assignments_select on public.assignments
    for select using (has_client_access(client_id, assigned_by));
-- By hand: those who may edit the company, as themselves. Rule assignments
-- are written by the app with the service role (a read-only viewer can open
-- the page that routes a new task).
drop policy if exists assignments_insert on public.assignments;
create policy assignments_insert on public.assignments
    for insert with check (can_edit_client(client_id, assigned_by)
                           and assigned_by = (select auth.uid()) and source = 'manual');

-- ── Routing rules: who handles which area, per company ──────────────────
create table if not exists public.routing_rules (
    id           uuid primary key default gen_random_uuid(),
    client_id    uuid not null references public.clients (id) on delete cascade,
    area         text not null check (area in ('gdpr', 'nis2', 'ai_act', 'documents', 'incidents')),
    assignee_id  uuid not null references auth.users (id) on delete cascade,
    updated_by   uuid references auth.users (id) on delete set null,
    updated_at   timestamptz not null default now(),
    unique (client_id, area)
);
alter table public.routing_rules enable row level security;
drop policy if exists routing_rules_select on public.routing_rules;
create policy routing_rules_select on public.routing_rules
    for select using (has_client_access(client_id, updated_by));
drop policy if exists routing_rules_insert on public.routing_rules;
create policy routing_rules_insert on public.routing_rules
    for insert with check (is_client_admin(client_id));
drop policy if exists routing_rules_update on public.routing_rules;
create policy routing_rules_update on public.routing_rules
    for update using (is_client_admin(client_id)) with check (is_client_admin(client_id));
drop policy if exists routing_rules_delete on public.routing_rules;
create policy routing_rules_delete on public.routing_rules
    for delete using (is_client_admin(client_id));

-- ── Comments on an item ──────────────────────────────────────────────────
-- Everyone with access to the company may comment, read-only included: a
-- question from the auditor or the DPO is discussion, not a change.
create table if not exists public.item_comments (
    id          uuid primary key default gen_random_uuid(),
    client_id   uuid not null references public.clients (id) on delete cascade,
    item_type   text not null check (item_type in ('task', 'incident')),
    item_key    text not null check (char_length(item_key) between 1 and 400),
    author_id   uuid references auth.users (id) on delete set null,
    body        text not null check (char_length(btrim(body)) between 1 and 4000),
    created_at  timestamptz not null default now()
);
create index if not exists item_comments_item_idx
    on public.item_comments (client_id, item_type, item_key, created_at);
alter table public.item_comments enable row level security;
drop policy if exists item_comments_select on public.item_comments;
create policy item_comments_select on public.item_comments
    for select using (has_client_access(client_id, author_id));
drop policy if exists item_comments_insert on public.item_comments;
create policy item_comments_insert on public.item_comments
    for insert with check (has_client_access(client_id, author_id)
                           and author_id = (select auth.uid()));

-- ── Notifications: one person's inbox ────────────────────────────────────
-- Written by the app with the service role (one person notifies another);
-- each reads and marks read only their own.
create table if not exists public.notifications (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references auth.users (id) on delete cascade,  -- recipient
    client_id   uuid not null references public.clients (id) on delete cascade,
    kind        text not null check (kind in ('assigned', 'comment', 'mention')),
    item_type   text not null check (item_type in ('task', 'incident')),
    item_key    text not null,
    item_title  text,
    actor_id    uuid references auth.users (id) on delete set null,
    created_at  timestamptz not null default now(),
    read_at     timestamptz
);
create index if not exists notifications_user_idx
    on public.notifications (user_id, read_at, created_at desc);
alter table public.notifications enable row level security;
drop policy if exists notifications_select on public.notifications;
create policy notifications_select on public.notifications
    for select using (user_id = (select auth.uid()));
drop policy if exists notifications_update on public.notifications;
create policy notifications_update on public.notifications
    for update using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

comment on table public.assignments is 'S56: who a task or incident is given to; history, newest row current.';
comment on table public.routing_rules is 'S56: default person per area, per company.';
comment on table public.item_comments is 'S56: comment thread on a task or incident (in-app only, D-05).';
comment on table public.notifications is 'S56: in-app inbox. Written with the service role.';
